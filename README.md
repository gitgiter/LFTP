# 1. LFTP
一个基于UDP实现的大文件可靠传输协议，使用python实现。

# 2. 架构设计
将LFTP分解为两个板块。

## 2.1 TCP
TCP板块使用UDP模拟实现可靠传输、流控制和拥塞控制。提供可靠传输的接口供FTP调用。
- 模仿socket——mysocket。

## 2.2 LFTP
LFTP板块负责调用TCP板块提供的可靠传输接口，进行文件传输。需要实现文件分片、重组以及多客户端支持、用户交互等。
- 客户端——LFTP_client。
- 服务端——LFTP_server。

---

**注：mysocket既是client也是server。**

---

## 2.3 接口设计
TCP板块提供以下接口供FTP调用：

- 用于服务端绑定本地端口。绑定成功返回true，端口被占用返回false。local_addr是一个(local_ip, local_port)的元组。
```python
mysocket.bind(local_addr) => bool
```

- 用于客户端绑定和连接服务端的ip地址和端口。连接成功返回true，失败返回false。remote_addr是一个(remote_ip, remote_port)的元组。
```python
mysocket.connect(remote_addr) => bool
```

- 用于服务端监听连接。监听到新的连接并握手成功返回true，失败返回false。num表示连接上限。
```python
mysocket.listen(num) => bool
```

- 用于服务端获取一个已握手的连接，该连接可以直接调用send和recv。返回值包括一个mysocket类型和一个元组remote_addr。
```python
mysocket.accpet() => (mysocket, remote_addr)
```

- 用于服务端或客户端发送数据。发送成功返回true，失败返回false。message必须是bytes。
```python
mysocket.send(message) => bool
```

- 用于服务端或客户端接收数据。该方法阻塞，直到接收到数据包，返回一个处理好的数据包。
```python
mysocket.recv(size) => bytes
```

## 2.4 TCP内部实现
采用面向对象进行接口封装。

### 2.4.1 数据结构设计
- 在utils中定义了一个packets类，将data用header+data的形式包装起来，通过udp去传输。这个类自带一个make_pkt方法，负责将这个类的打包成一个真正的字节流。
```python
class packet:

    def __init__(self):
        self.srcPort = 12000
        self.dstPort = 12000
        self.seqNum = 0
        self.ackNum = 0
        self.ack = 0
        self.syn = 0
        self.fin = 0
        self.rwnd_check = 0
        self.rwnd = 16
        self.data = b''

    def __str__(self):
        temp =  'srcPort: ' + str(self.srcPort) + '\n'
        temp += 'dstPort: ' +  str(self.dstPort) + '\n'
        temp += 'seqNum: ' +  str(self.seqNum) + '\n'
        temp += 'ackNum: ' +  str(self.ackNum) + '\n'
        temp += 'ack: ' +  str(self.ack) + '\n'
        temp += 'syn: ' +  str(self.syn) + '\n'
        temp += 'fin: ' +  str(self.fin) + '\n'
        temp += 'rwnd_check: ' +  str(self.rwnd_check) + '\n'
        temp += 'rwnd: ' +  str(self.rwnd) + '\n'
        temp += 'data len: ' + str(len(self.data))
        return temp

    def make_pkt(self):
        # print('===== make packet begin =====')
        # print(self)
        pkt = '{0:016b}'.format(self.srcPort)
        pkt += '{0:016b}'.format(self.dstPort)
        pkt += '{0:032b}'.format(self.seqNum)
        pkt += '{0:032b}'.format(self.ackNum)
        pkt += '{0:01b}'.format(self.ack)
        pkt += '{0:01b}'.format(self.syn)
        pkt += '{0:01b}'.format(self.fin)
        pkt += '{0:01b}'.format(self.rwnd_check)
        pkt += '{0:016b}'.format(self.rwnd)
        pkt = bytes(pkt, encoding='utf-8')
        if len(self.data) > 0:
            pkt += self.data
        # print('===== make packet end =====')
        return pkt
```
- 另外，对应地，在utils中还提供了一个extrac_pkt方法，这个方法不属于packet类。它负责将一个字节流解析成packet类型。
```python
def extract_pkt(pkt):
    # print('===== extract packet begin =====')
    # pkt = str(pkt[:116], encoding='utf-8')
    temp = packet()
    temp.srcPort = int(pkt[0:16], 2)
    temp.dstPort = int(pkt[16:32], 2)
    temp.seqNum = int(pkt[32:64], 2)
    temp.ackNum = int(pkt[64:96], 2)
    temp.ack = pkt[96] - 48
    temp.syn = pkt[97] - 48
    temp.fin = pkt[98] - 48
    temp.rwnd_check = pkt[99] - 48
    temp.rwnd = int(pkt[100:116], 2)
    if len(pkt) > 116:
        temp.data = pkt[116:]
    # print(temp)
    # print('===== extract packet end =====')
    return temp
```

### 2.4.2 mysocket各个接口实现思路
- bind。调用socket的bind。
- connect。三次握手的过程，客户端随机初始化一个seq（或0）。先发送一个SYN到服务端，等待服务端的SYN/ACK，收到的ACK序号应该等于seq+1，然后最后发送一个ACK返回给服务端。每次等待的时间不超过1s，最多等待3次。
```python
def connect(self, remote_addr):
    # print('===== handshake begin =====')
    # send SYN
    snd_pkt = utils.packet()
    snd_pkt.syn = 1
    # snd_pkt.seqNum = 0 or rand
    snd_pkt = snd_pkt.make_pkt()
    self.__sock.sendto(snd_pkt, remote_addr)
    # self.rdt_send(snd_pkt)
    print('connect: sended SYN to server (%s:%s)' % remote_addr)

    # wait for ACK
    try_count = 3
    while True:            
        try:
            # remote_addr is a tuple (ip, port)
            # recv_pkt, remote_addr = self.rdt_recv()
            recv_pkt, remote_addr = self.__sock.recvfrom(2048)
            recv_pkt = utils.extract_pkt(recv_pkt)
        except Exception as e:
            # no SYN from server, resend
            self.__sock.sendto(snd_pkt, remote_addr)
            # self.rdt_send(snd_pkt)
            print('connect: timeout, no SYN from server, resended SYN to server (%s:%s)' % remote_addr)
            try_count -= 1
            if try_count < 0:
                print('connect: fail to connect server (%s:%s)' % remote_addr)
                return False
            continue

        if recv_pkt.syn == 1 and recv_pkt.ack == 1 and recv_pkt.ackNum == self.__seq_num + 1:
            print('connect: received SYN/ACK from server (%s:%s)' % remote_addr)
            # send ACK to server
            snd_pkt = utils.packet()
            snd_pkt.ack = 1
            snd_pkt.ackNum = recv_pkt.seqNum + 1
            self.__seq_num = 0   # reset seqNum
            snd_pkt = snd_pkt.make_pkt()
            self.__sock.sendto(snd_pkt, remote_addr)
            # self.rdt_send(snd_pkt)
            print('connect: sended ACK to server (%s:%s)' % remote_addr)                
            self.__remote_addr = (remote_addr[0], recv_pkt.srcPort)
            break
    # print('===== handshake end =====\n')
    return True
```

- listen。监听连接的请求，如果收到来自客户端的SYN，返回一个SYN/ACK给客户端，然后等待一个客户端的ACK。由于服务端调用listen的时候不希望其阻塞，故这里开一个叫sub_listen的子线程（阻塞listen直到达到连接上限），由listen方法创建并执行该子线程。
```python
def listen(self, num):
    listen = threading.Thread(target=self.sub_listen, args=(num,))
    listen.start()
```

sub_listen在监听到SYN的时候就为客户端临时分配一个新的连接（使用新的端口），新的端口通过packet的srcPort属性传回给客户端从而通知客户端变更发送地址（原来是欢迎套接字，现在转换成连接套接字）。
```python
def sub_listen(self, num):
    # print('===== listen begin =====')
    while True:
        time.sleep(1)
        try:
            # recv_pkt, remote_addr = self.rdt_recv()
            if self.__client_count >= num:
                print('listen: reached max connection count')
                break
            recv_pkt, remote_addr = self.__sock.recvfrom(2048)
            recv_pkt = utils.extract_pkt(recv_pkt)
        except Exception as e:
            continue
        
        if recv_pkt.syn == 1:
            if remote_addr in self.__client_sock:
                # remote client exist
                continue
            
            self.__client_seq[remote_addr] = 0 # or rand
            snd_pkt = utils.packet()
            snd_pkt.seqNum = self.__client_seq[remote_addr]
            snd_pkt.ackNum = recv_pkt.seqNum + 1
            snd_pkt.ack = 1
            snd_pkt.syn = 1
            snd_pkt.srcPort = self.__local_addr[1] + 10 * (self.__client_count + 1)
            new_client_sock = mysocket(remote_addr=remote_addr)
            self.__client_sock[remote_addr] = new_client_sock
            new_client_sock.bind(('localhost', snd_pkt.srcPort))
            snd_pkt = snd_pkt.make_pkt()
            self.__sock.sendto(snd_pkt, remote_addr)
            # self.rdt_send(snd_pkt)
            print('listen: sended SYN to client (%s:%s)' % remote_addr)
        elif recv_pkt.ack == 1 and recv_pkt.ackNum == self.__client_seq[remote_addr] + 1:
            self.__client_count += 1               
    # print('===== listen end =====\n')
```
- accept。在mysocket内部维护了一个client_sock变量，这个变量保存了前面监听到的并成功握手的所有客户端及其对应的连接。当服务端调用accept的时候从client_sock里面取一个连接及其客户端地址并返回。如果client_sock长度为0，则阻塞等待。如果之前服务端在收到SYN时临时分配的连接并没有被最终ACK，则把这些多余的连接删除。
```python
def accept(self):
    while len(self.__client_sock) > self.__client_count:
        # those client who didn't send last ack for handshake
        keys = list(self.__client_sock.keys())
        self.__client_sock.pop(keys[-1])
    while len(self.__client_sock) == 0:
        time.sleep(1)
    keys = list(self.__client_sock.keys())
    return (self.__client_sock.pop(keys[0]), keys[0])
```
- send。使用了回退n的机制，将用户传进来的data进行进一步分片，如果分片数大于缓存，则不发送，以及如果分片数大于对方的rwnd也不发送。回退n循环调用rdt_send方法，rdt_send方法判断当前要发送的seq是否在窗口可发送的返回。
- recv。中间启动子线程循环接收包。接收到的包放到缓存中，每次被读出来的时候，清除缓存中的对应项。

## 2.5 FTP内部实现


## 2.6 分工
- 谢涛：TCP
- 谢玮鸿：FTP

# 3. 使用手册：

- Server和Client确保可以相互ping通（关掉防火墙）

- 客户端需要先安装progressbar库，显示进度条
	pip install progressbar

- Server需要修改FTP_server.py中的HOST为ip地址（可以为localhost）,默认的链接端口FTPPORT为3154，也可更改为其他可用端口

- Server可以修改FTP_server.py中的PATH，PATH为存放文件的地方，供client下载/上传

- Client可以修改FTP_client.py中的DOWNLOADPATH，即是下载后文件的存放路径

# 4. 测试

## 4.1 上传文件
## 4.2 下载文件
## 4.3 流控制
## 4.4 拥塞控制
## 4.5 多客户端
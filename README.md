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
- send。使用了回退n的机制，将用户传进来的data进行进一步分片，如果分片数大于缓存，则不发送，以及如果分片数大于对方的rwnd也不发送。回退n循环调用rdt_send方法，rdt_send方法判断当前要发送的seq是否在窗口可发送内的返回。

- recv。中间启动子线程循环接收包。接收到的包放到缓存中，每次被读出来的时候，清除缓存中的对应项。

- 拥塞控制  
拥塞控制算法主要包括慢启动、拥塞避免和快速恢复。  
TCP中维护两个变量：cwnd和ssthresh，一个是拥塞窗口，一个是慢启动阈值。cwnd初始为1，ssthresh初始为8。  
```python
self.__cwnd = 1
self.__ssthresh = 8
```  
**慢启动 & 拥塞避免**
在慢启动状态，cwnd的值以1个MSS开始，并且每当传输的报文段被确认，就增加一个MSS；在拥塞避免状态，每当cwnd个报文段被确认，cwnd的值就增加一个MSS。  
```python
if recv_pkt.ack == 1:
    # ...                 
    ack_count += 1
    if self.__cwnd < self.__ssthresh:
        self.__cwnd += 1    # slow start
    elif self.__cwnd >= self.__ssthresh and ack_count == n:
        self.__cwnd += 1    # congestion avoidance
```  

**快速恢复**
当丢包事件出现时，ssthresh的值更新为原来的一半，cwnd的值也更新为原来的一半，继续进行拥塞避免算法
```python
try_count = 3 # max resend times
while True:
    try:
        # ...
        try_count -= 1
        if try_count < 0:
            # fast recovery
            self.__cwnd = math.floor(self.__cwnd / 2)
            self.__ssthresh = math.floor(self.__ssthresh / 2)   
            return False
        continue
```

## 2.5 FTP内部实现
LFTP可以视作为调用自实现的类TCP接口的FTP程序。FTP板块负责调用TCP板块提供的可靠传输接口，进行文件传输。需要实现文件分片、重组以及多客户端支持、用户交互等。

客户端——client。
服务端——server。

FTP程序用于传输文件，一次传输需要两个TCP链接，一个是控制连接，一个是数据连接。此FTP程序采用主动模式，即服务端在控制连接上向客户端进行权限确认，确认之后打开数据连接的端口，并告知客户端该端口；客户端连接到该端口，进行数据传输。  

### 2.5.1 实现  
FTP的控制连接和数据连接分别占用一个线程（使用python的multiprocessing库实现）。控制连接的线程函数负责与用户交互，获取控制信息，然后开启一个线程用于数据传输。而数据连接专门负责进行数据传输。

此外，服务端维护两个队列`Queue`变量，一个是可用端口队列，一个是传输数据队列。Queue的功能是将每个核或线程的运算结果放在队列中，之后可以取出信息再作处理。这里两个线程可以通过这两个队列进行通信：当控制连接获取控制信息后，从可用端口队列中取出一个可用端口，用于建立一个新的数据连接；传输的数据则存放在传输数据队列中，一旦队列非空，就通过数据连接传输数据。

FTP文件传输流程图（按时间顺序从上往下）：
| 服务端（控制连接） | 服务端（数据连接） | 客户端 |
| ------ | ------ | ------ |
| 建立控制连接，开始监听（非阻塞） |  | 用户交互：输入服务端ip&port |
|  |  | 尝试连接服务端的控制连接端口 |
| 连接成功 | | |
|  |  | 用户交互：选择put/get操作 |
|  |  | 发送控制信息（操作、文件名、文件大小） |
| 将相应信息加入到数据队列 | 检测到数据队列非空，建立数据连接，开始监听 |
| 从可用端口队列中返回一个可用端口给客户端 |  |  |
| | |尝试连接服务端的数据连接端口 |
||连接成功，接收方发送ACK表示准备好接收文件||
||发送方发送文件（多线程）||
||传输完成，关闭数据连接|传输完成，继续进行用户交互|

### 2.5.2 重要代码  

- **维护Queue & 启动线程函数**

datas和ports存放传输数据和可用端口；cmdTrans线程函数管理控制连接，dataTrans线程函数管理数据连接。此程序最多允许10个用户进行put上传/get下载操作，ta们使用的数据连接将会被分配到9000-9009中的一个端口。
```python
if __name__=='__main__':
    datas = multiprocessing.Queue()     # 定义一个多线程队列，存放传输的数据
    ports = multiprocessing.Queue()     # 定义一个多线程队列，存放可用端口，此程序开放8000-8009端口
    for i in range(10):                 # 放入开放的端口
        ports.put(9000 + i)

    # 控制连接和数据连接分别定义两个线程函数
    cmdTrans = multiprocessing.Process(target = ControlConn, args = [datas, ports])
    dataTrans = multiprocessing.Process(target = DataConn, args = [datas, ports])
    
    # 启动线程
    cmdTrans.start() 
    dataTrans.start()
    cmdTrans.join()
    dataTrans.join()
```

- **服务端处理客户端的上传/下载请求**  

在控制连接中，服务端接收到客户端的上传/下载请求后，将相应的控制信息加进传输数据队列中，并向客户端返回一个可用的端口，准备进行数据传输。以下以上传操作为例：
```python
# 接受client的上传命令后的处理
def clientUpload(self, conn, size, name):
    if not self.portQueue.empty():
        temp = {}
        temp['port'] = self.portQueue.get()
        temp['action'] = 'upload'
        temp['filesize'] = size
        temp['extra'] = name
        self.dataQueue.put(temp)    # 向传输数据队列添加数据
        
        send = {'status':True, 'port':temp['port'], 'size':size}
        conn.send(json.dumps(send).encode('utf-8'))        # 向client发送上传确认
    else:
        error = {'status':False, 'reason':'The server resources are fully occupied, please try again later'}
        conn.send(json.dumps(error).encode('utf-8'))       # 端口已被占满
```  

- **客户端发送上传/下载请求 & 数据传输处理**  

客户端先发送一个请求，服务端的响应可见上一个步骤。之后就可以收到服务端的确认，并得知本次数据连接使用的端口，尝试建立数据连接。数据连接建立成功后，接收方会发送一个ACK，发送方将会收到ACK，然后开始进行数据传输。以上传操作为例：
```python
# 上传文件，输入文件路径和上传的文件名
def upload(self, path, filename):
    # 通过控制连接，向server发送数据传输请求
    filesize = os.path.getsize(path)
    data = {'action':'upload', 'filesize':filesize, 'filename':filename}
    data = json.dumps(data)
    self.cmd.send(data.encode('utf-8'))

    # 接收‘请求数据传输’的响应
    rcv = self.cmd.recv(1024)
    rcv = json.loads(rcv.decode('utf-8'))
    if rcv['status']:
        # 允许数据传输，则建立数据连接
        time.sleep(0.5)
        try:
            self.trans.connect((self.ipaddr, rcv['port']))
        except Exception as e:
            print('Connect failed')
            print(e)
            return False

        
        # 接受建立数据连接的确认
        rcv = self.trans.recv(1024)
        if rcv.decode('utf-8')!='ACK':
            print('Data transfer failed (no ACK received)')
            self.trans.close()
            return False
            
        # 通过数据连接，开始进行数据传输
        file = open(path,'rb')
        fileCount = 0
        print('\nUploading...')
        bar.start()
        for i in file:
            try:
                self.trans.send(i)
                fileCount += len(i)
                bar.update(int(fileCount/filesize * 100))
            except Exception as e:
                print(e)
        self.trans.close()
        bar.finish()
        print('\nUpload complete\n')
    else:
        print('Error: ' + rcv['reason'] + '\n')
        return False
```  

- **服务端的上传/下载操作处理**  

服务端发送/接受ACK后，开始进行数据传输。以上传操作为例：
```python
# 数据上传
def dataUpload(self, conn):
    if os.path.exists(PATH)==False:
        os.makedirs(PATH)
    file = open(PATH + self.extra, 'wb')
    conn.send('ACK'.encode('utf-8'))
    fileCount = 0
    while fileCount < self.filesize:
        try:
            data = conn.recv(5)
            if data:
                file.write(data)
                fileCount += len(data)
            else:
                raise ValueError('Data Transfer failed')
        except Exception as e:
            print(e)
            break
    print('Upload complete\n')
```

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
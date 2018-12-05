import mysocket as socket
import json
import os, sys, time

import multiprocessing
import threading
import select

# HOST = '127.0.0.1'
# HOST = '192.168.199.154'
HOST = '172.18.35.238'
FTPPORT = 3154
PATH = os.path.dirname(os.path.abspath(__file__))+'\\Server\\' # FTP_Server.py的同级目录中的Server目录

# 控制连接类
class controlServer:
    def __init__(self, **kwargs):
        self.ipaddr =kwargs['ip']                   # server的ip
        self.port = kwargs['port']                  # ftp端口
        self.portQueue =kwargs['portQueue']         # 存放端口的队列
        self.dataQueue = kwargs['dataQueue']        # 存放传输数据的队列
        self.mySocket = socket.mysocket()
        print('Server system init!\n')

    # 建立控制连接
    def connect(self):
        self.mySocket.bind((self.ipaddr, self.port))    # 将server的端口号和该socket关联起来
        self.mySocket.listen(100)                       # 请求连接最大为100
        while True:
            conn, addr = self.mySocket.accept()
            self.interface(conn)
            # conn.close()
        # self.mySocket.setblocking(False)
        # read_list = [self.mySocket.get_socket()]
        # while True:
        #     readable, writeble, errored = select.select(read_list, [], [])
        #     for s in readable:
        #         if s is self.mySocket.get_socket():
        #             print('Get a connection')
        #             conn, addr = self.mySocket.accept()     # 当有client请求时，创建一个新套接字，由该client专用
        #             read_list.append(conn)
        #         else:
        #             if self.interface(s) == False:
        #                 s.close()
        #                 read_list.remove(s)                    # 两台主机之间传输控制信息的接口
        # # conn.close()                            # 关闭套接字

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

    # 接受client的下载命令后的处理
    def clientDownload(self, conn, filename):
        path = PATH + filename
        if os.path.isfile(path)==False:
            error = {'status':False, 'reason':'This file is not exist'}
            conn.send(json.dumps(error).encode('utf-8'))
            return

        if not self.portQueue.empty():
            temp = {}
            temp['port'] = self.portQueue.get()
            temp['action'] = 'download'
            temp['filesize'] = os.path.getsize(path)
            temp['extra'] = path
            self.dataQueue.put(temp)    # 向传输数据队列添加数据

            send = {'status':True, 'port':temp['port'], 'size':temp['filesize']}
            conn.send(json.dumps(send).encode('utf-8'))         # 向client发送下载确认
        else:
            error = {'status':False, 'reason':'The server resources are fully occupied, please try again later'}
            conn.send(json.dumps(error).encode('utf-8'))        # 端口已被占满

    # 等待client的命令，并作相应的处理
    def interface(self, conn):
        data = None
        try:
            data = conn.recv(5)
        except Exception as e:
            print(e)

        if data:
            package = json.loads(data.decode('utf-8'))
            action = package.get('action',None)
            if action == 'download':
                self.clientDownload(conn, package['filename'])
            elif action == 'upload':
                filesize = package.get('filesize',None)
                self.clientUpload(conn, filesize, package['filename'])
            else:
                error = {'status':False, 'reason':'Wrong command'}
                conn.send(json.dumps(error).encode('utf-8'))
            return True
        else:
            print('Disconnect')
            return False

# .............................................
# 数据链接类
class dataServer:
    def __init__(self,**kwargs):
        self.ipaddr = kwargs['ip']
        self.port = kwargs['port']
        self.action = kwargs['action']
        self.extra = kwargs['extra']
        self.filesize = kwargs['filesize']
        self.mySocket = socket.mysocket()

    # 建立数据连接
    def connect(self):
        self.mySocket.bind((self.ipaddr,self.port))
        self.mySocket.listen(10)
        while True:
            conn, addr = self.mySocket.accept() 
            if(self.action == 'download'):
                self.dataDownload(conn)
            elif(self.action == 'upload'):
                self.dataUpload(conn)
            conn.close()
        print('Close the port')

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

    # 数据下载
    def dataDownload(self, conn):
        file = open(self.extra, 'rb')
        try:
            rcv = conn.recv(5)
            if rcv.decode('utf-8') != 'ACK':
                raise ValueError('Wrong signal (no ACK received)')
        except Exception as e:
            print(e)
            return

        fileCount = 0
        for i in file:
            while True:
                try:
                    conn.send(i)
                    fileCount += len(i)
                    break
                except Exception as e:
                    print(e)
                    return
        print('Download complete\n')

# ......................................

# 控制连接线程函数
def ControlConn(*args):
    datas = args[0]
    ports = args[1]
    x = controlServer(ip = HOST, port = FTPPORT, portQueue = ports, dataQueue = datas)
    try:
        x.connect()
    except Exception as e:
        print(e)
        print('Control Connect failed')

# 数据连接线程函数
def DataConn(*args):
    datas = args[0]
    ports = args[1]
    while True:
        # 只要队列里还有数据，立即发送
        if not datas.empty():
            data = datas.get()
            print('Starting Transfer :')
            print(' port: %s'%data['port'])
            print(' action: %s'%data['action'])
            print(' filename: %s'%data['extra'])
            print(' filesize: %s KB'%(int(data['filesize'])/1024))            
            x = threading.Thread(target = open_server, args = [ports, data['port'], data['action'], data['extra'], data['filesize']])
            x.start()
            time.sleep(0.2)

def open_server(*args):
    server = dataServer(ip = HOST, port = args[1], action = args[2], extra = args[3], filesize = args[4])
    server.connect()
    print('port %s is free'%args[1])
    args[0].put(args[1])

# ......................................................

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
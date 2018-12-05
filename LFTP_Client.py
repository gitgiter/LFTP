import mysocket as socket
import json
import os, sys, time
import progressbar

# 下载路径
DOWNLOADPATH = os.path.dirname(os.path.abspath(__file__))+'\\Download\\' # FTP_Client.py的同级目录中的Download目录
bar = progressbar.ProgressBar()

class ftpClient:
    def __init__(self):
        self.cmd = socket.mysocket()      # 创建控制连接的socket
        self.trans = socket.mysocket()    # 创建数据连接的socket
        print('Client system init!\n')

    # 连接server的指定端口
    def connect(self, **kwargs):
        try:
            ip = kwargs['ip']
            port = int(kwargs['port'])
            if self.cmd.connect((ip, port)):
                self.ipaddr = ip
                return True
            else:
                return False
        except Exception as e:
            print(e)
            return False

    # 上传文件，输入文件路径和上传的文件名
    def upload(self, path, filename):
        # 通过控制连接，向server发送数据传输请求
        filesize = os.path.getsize(path)
        data = {'action':'upload', 'filesize':filesize, 'filename':filename}
        data = json.dumps(data)
        self.cmd.send(data.encode('utf-8'))

        # 接收‘请求数据传输’的响应
        rcv = self.cmd.recv(5)
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
            rcv = self.trans.recv(5)
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

    # 下载文件，指定文件路径    
    def download(self, filename):
        # 通过控制连接，像server发送数据传输请求
        data = {'action':'download', 'filename':filename}
        data = json.dumps(data)
        self.cmd.send(data.encode('utf-8'))

        # 接收‘请求数据传输’的响应
        rcv = self.cmd.recv(5)
        rcv = json.loads(rcv.decode('utf-8'))
        if rcv['status']:
            # 允许数据传输，则建立数据连接
            time.sleep(0.5)
            try:
                self.trans.connect((self.ipaddr, rcv['port']))
            except Exception as e:
                print('Connect failed')
                print(e)
                return

            if os.path.exists(DOWNLOADPATH)==False:
                os.makedirs(DOWNLOADPATH)
            file=open(DOWNLOADPATH + filename,'wb')
            time.sleep(0.5)
            self.trans.send('ACK'.encode('utf-8'))
            fileCount = 0
            filesize = rcv['size']
            print('\nDownloading...')
            bar.start()
            while fileCount < filesize:
                try:
                    data = self.trans.recv(5)
                    if data:
                        fileCount += len(data)
                        file.write(data)
                        bar.update(int(fileCount/filesize * 100))
                    else:
                        raise ValueError('Data Transfer failed')
                except Exception as e:
                    print(e)
                    break
            self.trans.close()
            file.close()
            bar.finish()
            print('\nDownload complete [DownloadPath: ./Download/]\n')
        else:
            print('Error: ' + rcv['reason'] + '\n')
            return 

    def Shell(self):
        # 连接到server
        while True:
            ipaddr = input('Input the ip address of the server : ')
            port = input('Input the port of the server : ')
            print('Connecting...')
            if self.connect(ip=ipaddr, port=port):
                break
        print('Connect successfully\n')

        # 进行用户操作
        while True:
            order = input('Command:\n 1. Upload File\n 2. Download File\n 3. Exit\n>> ')
            if order == '1' :
                path = input('Input the file path(absolute path) : ')
                if os.path.isfile(path):
                    filename = os.path.basename(path)
                    self.upload(path, filename)
                    self.trans.close()
                    self.trans = socket.mysocket()
                else:
                    print('This path is not exist')
            elif order == '2':
                filename = input('Input the file name : ')
                self.download(filename)
                self.trans.close()
                self.trans = socket.mysocket()
            elif order == '3':
                return
            else:
                print('Invalid command.')



if __name__=='__main__':
    x=ftpClient()
    x.Shell()
    sys.exit(0)
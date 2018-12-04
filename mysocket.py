import utils
import socket
import math
import time
import threading

class mysocket:

    def __init__(self, remote_addr=('localhost', 12000)):
        self.__sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)        
        self.__sock.settimeout(1)
        self.__seq_num = 0
        self.__ack_num = 0
        self.__base = 0
        self.__sndpkt_buffer_size = 16
        self.__sndpkt_buffer = {}
        self.__rcvpkt_buffer_size = 16
        self.__rcvpkt_buffer = {}
        self.__remote_addr = remote_addr
        self.__client_sock = {}
        self.__client_seq = {}
        self.__client_count = 0
        self.__MSS = 1024
        self.__recv_started = False

    def bind(self, local_addr):
        self.__sock.bind(local_addr)
        
    def connect(self, remote_addr):
        print('===== handshake begin =====')
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
                recv_pkt, remote_addr = self.__sock.recvfrom(1024)
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
        print('===== handshake end =====\n')
        return True

    def listen(self, num):
        listen = threading.Thread(target=self.sub_listen, args=(num,))
        listen.start()    

    def sub_listen(self, num):
        print('===== listen begin =====')
        while True:
            time.sleep(1)
            try:
                # recv_pkt, remote_addr = self.rdt_recv()
                if self.__client_count >= num:
                    print('listen: reached max connection count')
                    break
                recv_pkt, remote_addr = self.__sock.recvfrom(1024)
                recv_pkt = utils.extract_pkt(recv_pkt)
            except:
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
                snd_pkt.srcPort = 13000 + self.__client_count                
                new_client_sock = mysocket(remote_addr=remote_addr)
                self.__client_sock[remote_addr] = new_client_sock
                new_client_sock.bind(('localhost', 13000 + self.__client_count))
                snd_pkt = snd_pkt.make_pkt()
                self.__sock.sendto(snd_pkt, remote_addr)
                # self.rdt_send(snd_pkt)
                print('listen: sended SYN to client (%s:%s)' % remote_addr)
            elif recv_pkt.ack == 1 and recv_pkt.ackNum == self.__client_seq[remote_addr] + 1:
                self.__client_count += 1                
        
        print('===== listen end =====\n')

    def accept(self):
        while len(self.__client_sock) > self.__client_count:
            # those client who didn't send last ack for handshake
            keys = list(self.__client_sock.keys())
            self.__client_sock.pop(keys[-1])
        while len(self.__client_sock) == 0:
            time.sleep(1)
        keys = list(self.__client_sock.keys())
        return (self.__client_sock.pop(keys[0]), keys[0])            

    def close(self):
        print('closed socket')
        self.__client_count -= 1
        self.__sock.close()
        
    # param: pkt is a packet object
    # return: true or false
    def rdt_send(self, pkt):        
        if self.__seq_num < self.__base + self.__sndpkt_buffer_size:
            pkt.seqNum = self.__seq_num
            self.__sndpkt_buffer[self.__seq_num] = pkt.make_pkt()
            self.__sock.sendto(self.__sndpkt_buffer[self.__seq_num], self.__remote_addr)
            if self.__base == self.__seq_num:
                # start_timer()
                pass
            self.__seq_num += 1
            return True
        else:
            # refuse_data()
            print('can not send yet')
            pass
            return False
        
    # return true or block to timeout
    def send(self, data):
        print('===== send begin =====')
        print('send buffer used:', len(self.__sndpkt_buffer), '(before send)')
        n = math.ceil(len(data) / (self.__MSS * 8))
        if n > self.__sndpkt_buffer_size:
            print('data too long, please make it smaller and resend')
            return False
        for i in range(n - 1):
            snd_pkt = utils.packet()
            snd_pkt.seqNum = self.__seq_num  
            snd_pkt.data = data[i*self.__MSS : (i+1)*self.__MSS]
            while self.rdt_send(snd_pkt) == False:
                pass

        snd_pkt = utils.packet()
        snd_pkt.seqNum = self.__seq_num
        snd_pkt.data = data[(n-1)*self.__MSS:]
        while self.rdt_send(snd_pkt) == False:
            pass
        print('send: sended', n, 'packets to (%s:%s)' % self.__remote_addr)

        try_count = 3 # max resend times
        while True:
            try:
                # recv_pkt, remote_addr = self.rdt_recv()   
                recv_pkt, remote_addr = self.__sock.recvfrom(1024)
                recv_pkt = utils.extract_pkt(recv_pkt)
            except Exception as e:
                # receive timeout: resend
                for i in range(self.__base, self.__seq_num):
                    # resend the packet that not ack
                    self.__sock.sendto(self.__sndpkt_buffer[i], self.__remote_addr)
                print('send: timeout, not enough ACKs received, resended data to (%s:%s)' % self.__remote_addr)
                try_count -= 1
                if try_count < 0:
                    print('send: fail to send data to (%s:%s)' % self.__remote_addr)
                    return False
                continue
            
            if recv_pkt.ack == 1:
                print('send: received ACK from (%s:%s)' % remote_addr)
                self.__base = recv_pkt.ackNum + 1
                if self.__base == self.__seq_num:
                    self.__sndpkt_buffer.clear()
                    break
            
        print('===== send end =====\n')
        return True

    # return: packet object or block to timeout
    def sub_recv(self):
        if len(self.__rcvpkt_buffer) > self.__rcvpkt_buffer_size:
            print('recv: buffer full')
            # return None, None

        while True:
            try:
                # remote_addr is a tuple (ip, port)
                recv_pkt, remote_addr = self.__sock.recvfrom(1024)
                recv_pkt = utils.extract_pkt(recv_pkt)
            except:
                # no packet received
                # print('recv: idle...')
                continue
                # return None, None
                
            # todo expected_seq
            if recv_pkt.ack == 0:
                self.__rcvpkt_buffer[recv_pkt.seqNum] = recv_pkt
                print('recv: received packet from (%s:%s)' % remote_addr)
                snd_pkt = utils.packet()
                snd_pkt.ack = 1
                snd_pkt.ackNum = recv_pkt.seqNum
                snd_pkt.rwnd = self.__rcvpkt_buffer_size - len(self.__rcvpkt_buffer)
                snd_pkt = snd_pkt.make_pkt()
                self.__sock.sendto(snd_pkt, remote_addr)
                print('recv: sended ACK to (%s:%s)' % remote_addr)
             
        # return recv_pkt, remote_addr

    def rdt_recv(self):
        if self.__recv_started == False:
            recv = threading.Thread(target=self.sub_recv)
            recv.start()
            self.__recv_started = True

    def recv(self, size):
        print('\n===== receive begin =====')        

        if size > self.__rcvpkt_buffer_size:
            print('read too much')
            return None

        if size == 0:
            print('read too less')

        # todo
        # recv_count = 0
        # while recv_count < size:
        #     recv_pkt, remote_addr = self.rdt_recv()
        #     if recv_pkt is None:
        #         time.sleep(1)
        #         continue
        #     recv_count += 1
        self.rdt_recv()
        
        # while True:
        #     try:
        #         while len(self.__rcvpkt_buffer) < size:
        #             # wait for recv
        #             time.sleep(1)
        #             pass
        #     except:
        #         if len(self.__rcvpkt_buffer) == 0:
        #             continue
        #         else:
        #             break
        sleep_count = 10
        while len(self.__rcvpkt_buffer) < size:
            time.sleep(0.5)
            sleep_count -= 1            
            if sleep_count < 0:
                if len(self.__rcvpkt_buffer) > 0:
                    break
                else:
                    sleep_count += 1
            pass

        data = b''
        length = len(self.__rcvpkt_buffer)
        read_count = 0
        keys = list(self.__rcvpkt_buffer.keys())
        for i in range(length):
            if read_count >= size or read_count >= length:
                break
            temp = self.__rcvpkt_buffer.pop(keys[i])
            data += temp.data
            read_count += 1
        
        print('===== receive end =====\n')
        return data

    def setblocking(self, block):
        self.__sock.setblocking(block)
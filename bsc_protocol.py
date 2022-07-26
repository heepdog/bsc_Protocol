#from curses.ascii import ENQ, EOT, ETB, NAK, SOH, STX, ETX, ACK
import logging
import serial
import serial.tools.list_ports as ports

SOH = b'\x01'
STX = b'\x02'
ETX = b'\x03'
EOT = b'\x04'
ENQ = b'\x05'
DLE = b'\x10'
ACK = b'\x10'
ACK0 = b'\x10\x30'
ACK1 = b'\x10\x31'
NAK = b'\x15'
ETB = b'\x17'

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("BSC_LOG")
log.info("hello")



class bscframe():
    def __init__(self) -> None:
        
        self.text: bytearray
        
        self.frame_number=0
        self.header_frame = False
        self.heading: bytes
        self.text =  bytearray()
        self.end_frame: bytes
        self.bcc: bytes
        self.bcc_sum = 0
    
    
class bscstream():
    def __init__(self) -> None:
       
        self.frames = list()
        self.frame_count = 0
        self.last_ack = 1
        
    def append_frame(self, frame):
        self.frames.append(frame)
        self.frame_count += 1
        
        
    
    def print_header(self):
        for frame in self.frames:
            if frame.header_frame:
                print(f"Heading: {frame.heading}  Text: {frame.text}")
                
    def get_header_text(self) -> str:
        for frame in self.frames:
            if frame.header_frame:
                return frame.text.decode('UTF-8')
    
    def get_heading(self) -> str:
        for frame in self.frames:
            if frame.header_frame:
                return frame.heading.decode('UTF-8')

    def print_data(self):
        for frame in self.frames:
            if not frame.header_frame:
                print(frame.text.decode('UTF-8'),end="",flush=True)
                
    def get_data(self) -> str:
        data = ""
        for frame in self.frames:            
            if not frame.header_frame:
                data = data+ frame.text.decode("UTF-8")
        return data
    
    def get_stream(self, link: serial):
        link.flushInput()
        link.flush()

        tries = 0
        next_bit = NAK
        log.info("looping for frames")
        while tries != 1 :
            frame = bscframe()
            log.info("waiting for inital comand code")
            next_bit = link.read(1)
            
            if len(next_bit) == 0:
                tries +=1
            else:
                tries = 0
            
            # if byte is a start of header character set header frame to true and read the next six chars as the header
            # should add a stream type to bscstream depending on the heading that was recieved
            # Assuming save header "02,001" initially
            log.info(f'Comparing {next_bit} to {SOH}')
            if next_bit == SOH:
                log.info("got Header command code")
                frame.header_frame = True
                frame.heading = link.read(6)
                for x in frame.heading:
                    frame.bcc_sum +=  int(x)
                log.info(f'header: {frame.heading}')
                # TODO: depending on the header type jump to requested operation, for now assume save file.
                next_bit = link.read(1) # get next control character, should always be STX after a heading
                frame.bcc_sum += int.from_bytes(next_bit,"little")
                log.info(f'Next ctl char reiceved {next_bit}')
                # TODO: error handling for error in next bit
            
            if next_bit ==STX:
                log.info(f'Recieved stx: {next_bit}')
            
                while True:
                    next_bit = link.read(1)
                    frame.bcc_sum += int.from_bytes(next_bit,"little")
                    # print(next_bit.decode("ascii"),end="",flush=True)
                    if (next_bit == ETB):
                        # getbcc(frame.text.extend(next_bit))
                        log.info(f'Got ETB: {next_bit}')
                        break
                    elif (next_bit == ETX):
                        log.info(f'Got ETX: {next_bit}')
                        break
                    else:
                        frame.text.extend(next_bit)
                
                log.info(len(frame.text))
                frame.bcc = link.read(2)    # TODO: should add error handling for differing BCC
                if frame.bcc != frame.bcc_sum:
                    raise BccError(f'Bcc Errror - Recieved: {frame.bcc}, Calculated: {frame.bcc_sum}')
                # log.info(f'Recieved BCC: {frame.bcc}; Computed BCC: {getbcc(frame.text)}; added BCC: {frame.bcc_sum.to_bytes(length=2,byteorder="little",signed=False)}')
                # log.info(f'Recieved BCC: {int.from_bytes(frame.bcc, "little")}; Computed BCC: {getbcc(frame.text)}; added BCC: {frame.bcc_sum}')
                self.append_frame(frame)
                link.write(ACK0 if (self.frame_count % 2==0) else ACK1)

                
            
            elif next_bit == ENQ:
                log.info(f'Starting Frame Recieved ENQ: {next_bit}')
                link.write(ACK0)
                
            elif next_bit == EOT:
                log.info(f'Ending frame Recieved EOT: {next_bit}')
                break
            else:
                pass
                # print(next_bit)
        # End of frame Here
        
        # Read transmission to decide what to do next
        if self.get_heading() == "02,001":
            log.info("writing enq")
            link.write(ENQ)
            # next_bit = link.read(1) # TODO: Error check for positive ACK
            # log.info(f'recieved: {next_bit}')
            # next_bit = link.read(1) # TODO: Error check for positive ACK
            # log.info(f'recieved: {next_bit}')
            self.get_ack(link)
            ack_str = b'90,000\x020000\r\x03' # assumes all went properly
            # link.write(SOH)
            # link.write(ack_str)
            # link.write(getbcc(ack_str))
            self.send_frame(link,SOH,ack_str)
            # next_bit = link.read(1) # TODO: Error check for positive ACK
            # log.info(f'recieved: {next_bit}')
            # next_bit = link.read(1) # TODO: Error check for positive ACK
            self.get_ack(link)
            log.info(f'recieved: {next_bit}')
            link.write(EOT)
            # TODO: Save texts from frames as file with filename from header frame text
            
            with open(self.get_header_text().strip() + '.JBI','w') as fs:
                fs.write(self.get_data())
            log.info("File Written")

            
            
        elif self.get_heading() == "02,051":
            # TODO: setup send of file with name from header text.to_bytes(length=2,byteorder="little",signed=False)
            filename = self.get_header_text().strip()
            log.info(f'Sending File: {filename}')
            link.write(ENQ)
            link.read(1)    # TODO: should add error handling for NAK
            link.read(1)    # TODO: should add error handling for NAK
            send_string = bytearray(b'02,001\x02')
            send_string.extend(bytearray(self.get_header_text(),"UTF-8"))
            send_string.extend(ETB)
            # link.write(SOH)
            # link.write(send_string)
            # link.write(getbcc(send_string))
            self.send_frame(link,SOH,send_string)
            link.read(2)    # TODO: should add error handling for NAK
            
            with open(filename + '.JBI', "rb") as fd:
                eof = False
                file_size = LengthOfFile(fd)
                log.info(f'filesize: {file_size}')
                while not eof:
                    send_data = fd.read(256)
                    # if len(send_data)<256:
                    if fd.tell() == file_size:
                        Bytestr = send_data+ETX
                        eof = True
                    else:
                        Bytestr = send_data+ETB
                        # log.info(Bytestr)

                    if send_data:
                        # link.write(STX)
                        # link.write(Bytestr)
                        # link.write(getbcc(Bytestr))
                        self.send_frame(link,STX,Bytestr)
                        # log.info(f'{STX:02x},{Bytestr.hex(",")},{getbcc(Bytestr).hex(",")}')
                    # link.read(1) # TODO: should add error handling for NAK
                    # link.read(1) # TODO: should add error handling for NAK
                    self.get_ack()
            # Done sending file
            link.write(EOT)
            
            
            pass
        else:
            print(f'Unknown Header {self.get_heading()}')
            
            
    def send_frame(self, link, cmd, data):
        link.write(cmd)
        link.write(data)
        link.write(getbcc(data))
        
    def get_ack(self, link):
        ack_val = link.read(1)
        if ack_val == ACK:
            ack_val = link.read(1)
            if ack_val != self.last_ack:
                self.last_ack = ack_val
            else:
                raise SendError("ACK Order Error")
        elif ack_val == NAK:
            raise SendError("NAK Recieved")
        else:
            raise SendError(f'Expecting ACK, Recieved {ack_val}')
        
class SendError(Exception):
    pass
class BccError(Exception):
    pass

            
def getbcc(datastring) -> bytes:
        data = 0
        for d in datastring:
            data = data+int(d)
        return data.to_bytes(length=2,byteorder="little",signed=False)

def LengthOfFile(f):
    """ Get the length of the file for a regular file (not a device file)"""
    currentPos=f.tell()
    f.seek(0, 2)          # move to end of file
    length = f.tell()     # get current position
    f.seek(currentPos, 0) # go back to where we started
    return length
        
def BytesRemaining(f,f_len):
    """ Get number of bytes left to read, where f_len is the length of the file (probably from f_len=LengthOfFile(f) )"""
    currentPos=f.tell()
    return f_len-currentPos
    

def getlink() -> serial:
    """ Main entry to program
    """
    available_ports = ports.comports()
    
    print("Available Ports:")
    id = 1
    
    for f in available_ports:
        print(f'{id}) {f.name}:  {f.description} {f.device}')
        id += 1
        
    port_id = input("Choose Port: ")
    
    port_id = int(port_id)
    # default_baud = 115200
    default_baud = 9600
    default_stop = 1
    default_parity = serial.PARITY_NONE
    default_timeout = 15
    link = serial.Serial(available_ports[port_id-1].device, default_baud, parity = default_parity,timeout = default_timeout, stopbits = default_stop)
    link.flushInput()
    
    link.flush()
    return link
    # tmp = bscstream()
    # print(getbcc(b'\x0f\x0a'))
    #tmp.get_stream(link)
    
    # link.write([ACK,0X30])
    # start_byte: bytes = link.read(1)
    # if start_byte == ENQ:
    #     print("Recieved Enquery, Starting Transfer")
        
    # else:
    #     print(f'Serial port Recieved ({start_byte.hex()}) ')
    # link.close()
    
def save_file():
    serial_link = getlink()
    stream = bscstream()
    serial_link.flushInput()
    while(1):
        stream.get_stream(serial_link)
    # stream.print_header()
    # stream.print_data()
    # fs = open(stream.get_header_text().strip(),'w')
    # fs.write(stream.get_data())

if __name__ == "__main__":
    log.info("hello")
    save_file()
    
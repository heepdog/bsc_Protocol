from curses.ascii import ENQ, EOT, ETB, NAK, SOH, STX, ETX, ACK
import logging
import serial
import serial.tools.list_ports as ports


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
            if int.from_bytes(next_bit,"little") == SOH:
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
            
            if int.from_bytes(next_bit,"little") ==STX:
                log.info(f'Recieved stx: {next_bit}')
            
                while True:
                    next_bit = link.read(1)
                    frame.bcc_sum += int.from_bytes(next_bit,"little")
                    # print(next_bit.decode("ascii"),end="",flush=True)
                    if (int.from_bytes(next_bit,"little") == ETB):
                        # getbcc(frame.text.extend(next_bit))
                        log.info(f'Got ETB: {next_bit}')
                        break
                    elif (int.from_bytes(next_bit,"little") == ETX):
                        log.info(f'Got ETX: {next_bit}')
                        break
                    else:
                        frame.text.extend(next_bit)
                
                log.info(len(frame.text))
                frame.bcc = link.read(2)    # TODO: should add error handling for differing BCC
                # log.info(f'Recieved BCC: {frame.bcc}; Computed BCC: {getbcc(frame.text)}; added BCC: {frame.bcc_sum.to_bytes(length=2,byteorder="little",signed=False)}')
                log.info(f'Recieved BCC: {int.from_bytes(frame.bcc, "little")}; Computed BCC: {getbcc(frame.text)}; added BCC: {frame.bcc_sum}')
                self.append_frame(frame)
                link.write(b'\x10\x30' if (self.frame_count % 2==0) else b'\x10\x31')

                # self.frame_count += 1
            
            elif int.from_bytes(next_bit,"little") == ENQ:
                log.info(f'Starting Frame Recieved ENQ: {next_bit}')
                link.write(b'\x10\x30')
                
            elif int.from_bytes(next_bit,"little") == EOT:
                log.info(f'Ending frame Recieved EOT: {next_bit}')
                # link.write(b'\x10\x30')
                break
            else:
                pass
                # print(next_bit)
        # End of frame Here
        
        # Read transmission to decide what to do next
        if self.get_heading() == "02,001":
            log.info("writing enq")
            link.write(b'\x05')
            next_bit = link.read(1) # TODO: Error check for positive ACK
            log.info(f'recieved: {next_bit}')
            next_bit = link.read(1) # TODO: Error check for positive ACK
            log.info(f'recieved: {next_bit}')
            ack_str = b'90,000\x020000\r\x03' # assumes all went properlittle
            link.write(b'\x01')
            link.write(ack_str)
            link.write(getbcc(ack_str))
            next_bit = link.read(1) # TODO: Error check for positive ACK
            log.info(f'recieved: {next_bit}')
            next_bit = link.read(1) # TODO: Error check for positive ACK
            log.info(f'recieved: {next_bit}')
            link.write(b'\x04')
            # TODO: Save texts from frames as file with filename from header frame text
            
            with open(self.get_header_text().strip(),'w') as fs:
                fs.write(self.get_data())
            log.info("File Written")

            
            
        elif self.get_heading() == "02,051":
            # TODO: setup send of file with name from header text.to_bytes(length=2,byteorder="little",signed=False)
            filename = self.get_header_text().strip()
            log.info(f'Sending File: {filename}')
            link.write(ENQ)
            link.read(2)    # TODO: should add error handling for NAK
            send_string = bytearray(b'02,001\x02')
            send_string.extend(bytearray(self.get_header_text(),"UTF-8"))
            send_string.extend(ETB.to_bytes(1,"little"))
            link.write(SOH)
            link.write(send_string)
            link.write(getbcc(send_string))
            link.read(2)    # TODO: should add error handling for NAK
            
            with open(filename, "rb") as fd:
                eof = False
                file_size = LengthOfFile(fd)
                log.info(f'filesize: {file_size}')
                while not eof:
                    send_data = fd.read(256)
                    # if len(send_data)<256:
                    if fd.tell() == file_size:
                        Bytestr = send_data+ETX.to_bytes(1,"little")
                        eof = True
                    else:
                        Bytestr = send_data+ETB.to_bytes(1,"little")
                        # log.info(Bytestr)

                    if send_data:
                        link.write(STX)
                        link.write(Bytestr)
                        link.write(getbcc(Bytestr))
                        # log.info(f'{STX:02x},{Bytestr.hex(",")},{getbcc(Bytestr).hex(",")}')
                    link.read(2) # TODO: should add error handling for NAK
            # Done sending file
            link.write(EOT)
            
            
            pass
        else:
            print(f'Unknown Header {self.get_heading()}')

            
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
    
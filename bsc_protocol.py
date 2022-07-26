#from curses.ascii import ENQ, EOT, ETB, NAK, SOH, STX, ETX, ACK
import logging
from time import sleep
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
    """
    Class to setup a BSC-like Frame for MOTOMAN
    
    .............................................
    
    Attributes
    ---------------------------------------------
    text : bytearay
        data of the Frame
    frame_number : int
        number of sequence the frame was recieved
    header_frame : bool
        Designates if frame contains header info
    heading : bytes
        Recieved Heading of the frame
    bcc : bytes
        Recieved BCC from the transmission
    bcc_sum : int
        Calculated BCC as frame is recieved
        
    Methods
    ---------------------------------------------
    
    """
    def __init__(self) -> None:
        
        self.text: bytearray
        self.frame_number=0
        self.header_frame = False
        self.heading: bytes
        self.text =  bytearray()
        self.bcc: bytes
        self.bcc_sum = 0
    
    
class bscstream():
    """ 
    Class to recieve BSC-like frames from a serial port
    .............................................
    
    Attributes
    ---------------------------------------------
    
    frames : list(bscframe)
        list of recieved BSC-like Frames
    frame_count : int
        Number of frames reiceved
    last_ack
        Last reiceved ACK
        
    Methods
    ---------------------------------------------
    
    clear():
        Resets the stream and clears all data to start from scratch
    append_frame(frame):
        adds recieved frame to list of rames and increments frame count
    print_header()
        searches through the list of frames until it finds one that is a header
        it will then print the heading and the text
    
    """
    
    def __init__(self) -> None:
        """Initalizes BSC-like Protocol 
        """
        self.frames = list()
        self.frame_count = 0
        self.last_ack = 1
        
    def clear(self):
        """Clears all frames from the list and resets parameters
        """
        self.frames.clear()
        self.frame_count = 0
        self.last_ack = 1

    def append_frame(self, frame):
        """Adds frame to end of frames list and adds 1 to frame count

        Args:
            frame (bscframe): frame of dataa from BSC-like protocol
        """
        self.frames.append(frame)
        self.frame_count += 1
    
    def print_header(self):
        """searches and prints the Heading and text from the header frame
        """
        for frame in self.frames:
            if frame.header_frame:
                print(f"Heading: {frame.heading}  Text: {frame.text}")
                
    def get_header_text(self) -> str:
        """Finds Header frame and returns the data

        Returns:
            str: Text data from the Header Frame
        """
        for frame in self.frames:
            if frame.header_frame:
                return frame.text.decode('UTF-8')
    
    def get_heading(self) -> str:
        """Finds header frame and returns the heading

        Returns:
            str: Six character header (##,###) defining the contents of the stream
        """
        for frame in self.frames:
            if frame.header_frame:
                return frame.heading.decode('UTF-8')

    def print_data(self):
        """Prints the text recievce in the text frames
        """
        for frame in self.frames:
            if not frame.header_frame:
                print(frame.text.decode('UTF-8'),end="",flush=True)
                
    def get_data(self) -> str:
        """Loops through the frames and returns a string of the text

        Returns:
            str: data from all frames besides the header frame
        """
        data = ""
        for frame in self.frames:            
            if not frame.header_frame:
                data = data + frame.text.decode("UTF-8")
        return data
    
    def get_stream(self, link: serial):
        """automates the reciving of multiple frames.  
        Will process thse frames based on the heading that is recieved

        Args:
            link (serial): Serial port that has already been 
                opened and set up to recieve at the proper bitrate

        Raises:
            BccError: Sends error if the wrong ACK is recieved or
                if the recieved bcc does not match the calculated bcc
        """
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
                # TODO: error handling for error in next bit
            
            if next_bit ==STX:
                log.info(f'Recieved stx: {next_bit}')
            
                while True:
                    next_bit = link.read(1)
                    frame.bcc_sum += int.from_bytes(next_bit,"little")
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
                frame.bcc = link.read(2)   
                if frame.bcc != frame.bcc_sum.to_bytes(length=2,byteorder="little",signed=False):
                    raise BccError(f'Bcc Errror - Recieved: {frame.bcc}, Calculated: {frame.bcc_sum}')
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

        # Read transmission Header to decide what to do next
        pri,sec = self.get_heading().split(',')
        if pri == '02':
            if sec == "001":
                self.write_file(link, self.get_header_text().strip(), ".JBI")
            elif sec == "002":
                self.write_file(link, self.get_header_text().strip(), ".JBR")
            elif sec == "200":
                self.write_file( link, "TOOL", ".CND")
            elif sec == "201":
                self.write_file( link, "WEAV", ".CND")
            elif sec == "202":
                self.write_file( link, "UFRAME", ".CND")
            elif sec == "203":
                self.write_file( link, "ARCSRT", ".CND")
            elif sec == "204":
                self.write_file( link, "ARCEND", ".CND")
            elif sec == "232":
                self.write_file( link, "VAR", ".DAT")
            elif sec == "240":
                self.write_file( link, "SYSTEM", ".SYS")
            elif sec == "241":
                self.write_file( link, "ALMHIST", ".DAT")
            elif sec == "051":
                self.send_file(link,  self.get_header_text().strip(), ".JBI")
            elif sec == "052":
                self.send_file(link,  self.get_header_text().strip(), ".JBR")
            else:
                print(f'Unhandled Header {self.get_heading}')
        else:
            print(f'Unknown Header {self.get_heading()}')
            
    def write_file(self, link:serial, filename:str, ext : str):
        """Takes frames that were recieved,pulls out the text data and saves it to the 
        coresponding filename+ext

        Args:
            link (serial): Serial link that thas been opened for use
            filename (str): Filename to save data as
            ext (str): extension for filename
        """
        log.info("writing enq")
        link.write(ENQ)
        self.get_ack(link)
        ack_str = b'90,000\x020000\r\x03' # assumes all went properly
        self.send_frame(link,SOH,ack_str)
        sleep(.2)
        self.get_ack(link)
        sleep(.2)
        link.write(EOT)
        
        with open(filename + ext,'w') as fs:
            fs.write(self.get_data())
        log.info(f"File {self.get_header_text().strip() + ext} Written")
    
    def send_file(self, link:serial, filename:str, ext: str):
        """opens the coresponding file and sends it across the serial link using BSC-like protocol

        Args:
            link (serial): Serial link that thas been opened for use
            filename (str): file to send on link
            ext (str): Exension of file to send on link
        """
        log.info(f'Sending File: {filename}')
        link.write(ENQ)
        self.get_ack()
        send_string = bytearray(b'02,001\x02')
        send_string.extend(bytearray(self.get_header_text(),"UTF-8"))
        send_string.extend(ETB)
        self.send_frame(link,SOH,send_string)
        self.get_ack()
        with open(filename + ext, "rb") as fd:
            eof = False
            file_size = LengthOfFile(fd)
            log.info(f'filesize: {file_size}')
            while not eof:
                send_data = fd.read(256)
                if fd.tell() == file_size:
                    Bytestr = send_data+ETX
                    eof = True
                else:
                    Bytestr = send_data+ETB

                if send_data:
                    self.send_frame(link,STX,Bytestr)
                self.get_ack()
        # Done sending file
        link.write(EOT)
        
            
            
    def send_frame(self, link : serial, cmd : bytes, data : bytearray):
        """Sends data over serial link using BSC-like Protocol 

        Args:
            link (serial): Initiated serial link
            cmd (byte): BSC command for the frame
            data (bytearray): Data to send, including end of frame
        """
        link.write(cmd)
        link.write(data)
        link.write(getbcc(data))
        
    def get_ack(self, link : serial):
        """Retrieves acknowldgement that frame was sent successfully

        Args:
            link (serial): Initated serial link

        Raises:
            SendError: Raised after a non ACK/NAK command received
            SendError: Raised after incorrect ACK0/ACK1 received
            SendError: Raised after a NAK command is received
        """
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
    """ Get number of bytes left to read, where f_len is the length of the file (probably from f_len=LengthOfFile(f) )
    """
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
    link = serial.Serial(available_ports[port_id-1].device, default_baud,parity = default_parity,timeout = default_timeout, stopbits = default_stop)
    link.flushInput()
    
    link.flush()
    return link

    
def bsc_transfer():
    serial_link = getlink()
    stream = bscstream()
    serial_link.flushInput()
    try:
        while(1):
            stream.get_stream(serial_link)
            stream.clear()
    except KeyboardInterrupt:
        print("Shutting down Transfer")
    finally:
        serial_link.close()
        

if __name__ == "__main__":
    bsc_transfer()
    
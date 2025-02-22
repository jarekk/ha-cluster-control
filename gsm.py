from gsmmodem.modem import GsmModem
import threading
import queue
import time

class Gsm:
    def __init__(self, pin, notify_number, device):        
        self.pin = pin
        self.notify_number = notify_number
        if device is not None:
            self.modem = GsmModem(device, 115200)
            self.modem.smsTextMode = False # use PDU mode
        else:
            self.modem = None
        self.queue = queue.Queue()
        self.signalStrength = 0
        self.networkName = ""
        
    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.thread.start()


    def run(self):
        if self.modem is None:            
            return
        
        self.modem.connect(self.pin)
        while True:
            try:
                self.signalStrength = self.modem.signalStrength
                self.networkName = self.modem.networkName

                if self.modem.signalStrength > 0:
                    if not self.queue.empty():
                        event = self.queue.get()

                        if event["type"] == "sms":
                            self.modem.sendSms(event["recipient"], event["message"])
                        

                else:
                    self.modem.connect(self.pin)
                pass
            except TimeoutError as e:
                print("Timeout error in GSM thread: ", e)
                time.sleep(10)
            except Exception as e:
                print("Error in GSM thread: ", e)
                time.sleep(30)
                
            time.sleep(0.1)

    def send_sms(self, message):
        self.queue.put({"type": "sms", "recipient": self.notify_number, "message": message})

    def get_status(self):
        return {
            "signal": self.signalStrength,
            "network": self.networkName,
        }

    def check_sms(self):
        pass

    def close(self):
        self.modem.close()

    

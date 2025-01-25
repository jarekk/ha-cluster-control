from gsmmodem.modem import GsmModem

pin_code = "3242" # string
recipient_number = "+491739633486" # string
message = 'asdf'

modem = GsmModem('/dev/tty.usbmodem58A80477991', 115200)
modem.smsTextMode = True # use PDU mode
modem.connect(pin_code)
print("signal: ", modem.signalStrength)
print("smsc: ",modem.smsc)
modem.sendSms(recipient_number, message)

modem.close()

import plistlib,socket,struct,unittest
from unittest.mock import patch
from loc2.backend import usb_connect


class MuxSocket:
    def __init__(self,reply):
        payload=plistlib.dumps(reply);self.data=struct.pack('<IIII',16+len(payload),1,8,1)+payload
        self.sent=[];self.closed=False
    def settimeout(self,value):pass
    def connect(self,path):pass
    def sendall(self,data):self.sent.append(data)
    def recv(self,count):value,self.data=self.data[:count],self.data[count:];return value
    def close(self):self.closed=True
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class USBControlTests(unittest.TestCase):
    def devices(self):return {'DeviceList':[
        dict(DeviceID=9,Properties=dict(SerialNumber='selected',ConnectionType='Network')),
        dict(DeviceID=10,Properties=dict(SerialNumber='other',ConnectionType='USB')),
        dict(DeviceID=11,Properties=dict(SerialNumber='selected',ConnectionType='USB'))]}
    def test_connect_uses_selected_physical_usb_device_and_network_order_port(self):
        lookup=MuxSocket(self.devices());stream=MuxSocket({'Number':0})
        with patch('loc2.backend.socket.socket',side_effect=[lookup,stream]):
            self.assertIs(usb_connect('selected',32145),stream)
        body=plistlib.loads(stream.sent[0][16:])
        self.assertEqual(body['DeviceID'],11);self.assertEqual(body['PortNumber'],socket.htons(32145))
        self.assertTrue(lookup.closed);self.assertFalse(stream.closed)
    def test_network_record_is_never_a_usb_substitute(self):
        data=self.devices();data['DeviceList']=data['DeviceList'][:2]
        with patch('loc2.backend.socket.socket',return_value=MuxSocket(data)):
            with self.assertRaises(ConnectionError):usb_connect('selected',32145)
    def test_rejected_connection_closes_socket(self):
        lookup=MuxSocket(self.devices());stream=MuxSocket({'Number':3})
        with patch('loc2.backend.socket.socket',side_effect=[lookup,stream]):
            with self.assertRaises(ConnectionError):usb_connect('selected',32145)
        self.assertTrue(stream.closed)

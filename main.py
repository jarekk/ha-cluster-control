import PySimpleGUI as sg
from flask import Flask
from datetime import datetime
from threading import Thread
import multiprocessing
import subprocess
import time
import requests
import re
from raid import check_raid
import configparser
from docker import check_docker


app = Flask(__name__)

ping_data = {}
server_a_status = None
server_b_status = None

event_queue = multiprocessing.Queue()

# Read the configuration file
config = configparser.ConfigParser()
config.read('config.ini')


# ----------------------------------------------------------------  
# HTTP endpoints
# ----------------------------------------------------------------  

flask_thread = Thread(target=app.run, kwargs={'port':18080})

@app.route('/pingServerA')
def ping_a():
    global ping_data
    ping_data["ha_http_server_a"] = datetime.now()
    return {'message': 'Server A pinged at {}'.format(datetime.now())}

@app.route('/pingServerB')
def ping_b():
    global ping_data
    ping_data["ha_http_server_b"] = datetime.now()
    return {'message': 'Server B pinged at {}'.format(datetime.now())}


# ----------------------------------------------------------------  
# Server pings
# ----------------------------------------------------------------  

def ping_host(host):
    try:
        output = subprocess.check_output(['ping', '-c', '1', host])
        return True
    except subprocess.CalledProcessError:
        return False
    

def check_http(host):
    try:
        response = requests.get(f"http://{host}/")
        #print(response.text)
        if "Home Assistant" in response.text:
            return True
    except Exception:
        return False
    
    return False
                

def process_ping(queue, host, label):

    while True:
        result = ping_host(host)
        queue.put({"type": label, "time": datetime.now(), "result": result})
        time.sleep(10)

def process_http_check(queue, host, label):
    while True:
        result = check_http(host)
        queue.put({"type": label, "time": datetime.now(), "result": result})
        #print(f"HTTP result for {host}: {result}")    

        time.sleep(10)


def process_raid_check(queue, host, label):
    while True:
        result = check_raid(host)
        queue.put({"type": label, "time": datetime.now(), "result": result})
        #print(f"RAID result for {host}: {result}")    

        time.sleep(120)


def process_docker_check(queue, host, image, label):
    while True:
        result = check_docker(host, image)
        queue.put({"type": label, "time": datetime.now(), "result": result})
        #print(f"Docker result for {host}: {result}")    

        time.sleep(10)
            
processes = [
    multiprocessing.Process(target=process_ping, args=(event_queue,config.get('IPs','internet'),"ping_internet")),
    multiprocessing.Process(target=process_ping, args=(event_queue,config.get('IPs','router'),"ping_udm")),
    multiprocessing.Process(target=process_ping, args=(event_queue,config.get('IPs','main_switch'),"ping_main_switch")),
    multiprocessing.Process(target=process_ping, args=(event_queue,config.get('IPs','garden_switch'),"ping_garden_switch")),
    multiprocessing.Process(target=process_ping, args=(event_queue,config.get('IPs','backup_switch'),"ping_backup_switch")),
    multiprocessing.Process(target=process_ping, args=(event_queue,config.get('IPs','server_a'),"ping_server_a")),
    multiprocessing.Process(target=process_ping, args=(event_queue,config.get('IPs','server_b'),"ping_server_b")),
    multiprocessing.Process(target=process_http_check, args=(event_queue,"ha.home.internal","ha_request")),
    multiprocessing.Process(target=process_raid_check, args=(event_queue,config.get('IPs','server_a'),"raid_server_a")),
    multiprocessing.Process(target=process_raid_check, args=(event_queue,config.get('IPs','server_b'),"raid_server_b")),
    multiprocessing.Process(target=process_docker_check, args=(event_queue,config.get('IPs','server_a'),"homeassistant/home-assistant","ha_docker_server_a")),
    multiprocessing.Process(target=process_docker_check, args=(event_queue,config.get('IPs','server_a'),"zigbee2mqtt","z2m_docker_server_a")),
    multiprocessing.Process(target=process_docker_check, args=(event_queue,config.get('IPs','server_b'),"homeassistant/home-assistant","ha_docker_server_b")),
    multiprocessing.Process(target=process_docker_check, args=(event_queue,config.get('IPs','server_b'),"zigbee2mqtt","z2m_docker_server_b"))
]


# ----------------------------------------------------------------
# Main startup
# ----------------------------------------------------------------

infra_panel = [
    [sg.Text('    Infrastracture', size=(40, 1))],
    [sg.Text('Internet:', size=(15, 1)), sg.Text('', key='-INFRA_INTERNET-', size=(20, 1))],
    [sg.Text('Router:', size=(15, 1)), sg.Text('', key='-INFRA_ROUTER-', size=(20, 1))],
    [sg.Text('Main Switch:', size=(15, 1)), sg.Text('', key='-INFRA_SWITCH_MAIN-', size=(20, 1))],
    [sg.Text('Garden Switch:', size=(15, 1)), sg.Text('', key='-INFRA_SWITCH_GARDEN-', size=(20, 1))],
    [sg.Text('Backup Switch:', size=(15, 1)), sg.Text('', key='-INFRA_SWITCH_BACKUP-', size=(20, 1))],
    [sg.Text('Current HA:', size=(15, 1)), sg.Text('', key='-INFRA_CURRENT_HA-', size=(20, 1))],
]



# Define the layout for Server A and Server B panels
server_a_panel = [
    [sg.Text('    Server A Status and Controls', size=(40, 1))],
    [sg.Text('Last Server Ping:', size=(15, 1)), sg.Text('', key='-A_LASTPING-', size=(20, 1))],
    [sg.Text('Last HA Ping:', size=(15, 1)), sg.Text('', key='-A_LASTPING_HA-', size=(20, 1))],
    [sg.Text('Last HA Message:', size=(15, 1)), sg.Text('', key='-A_LASTMSG_HA-', size=(20, 1))],
    [sg.Text('Last Z2M Message:', size=(15, 1)), sg.Text('', key='-A_LASTMSG_Z2M-', size=(20, 1))],
    [sg.Text('HA Docker:', size=(15, 1)), sg.Text('', key='-A_HA_DOCKER-', size=(20, 1))],
    [sg.Text('Z2M Docker:', size=(15, 1)), sg.Text('', key='-A_Z2M_DOCKER-', size=(20, 1))],
    [sg.Text('RAID:', size=(15, 1)), sg.Text('', key='-A_RAID-', size=(20, 1))],


    [sg.Button('Restart Homeassistant', key='-RESTART_HA_A-', size=(30, 1))],
    [sg.Button('Stop Homeassistant', key='-STOP_HA_A-', size=(30, 1))],
    [sg.Button('Start Homeassistant', key='-START_HA_A-', size=(30, 1))],
]

server_b_panel = [
    [sg.Text('   Server B Status and Controls', size=(40, 1))],
    [sg.Text('Last Server Ping:', size=(15, 1)), sg.Text('', key='-B_LASTPING-', size=(20, 1))],
    [sg.Text('Last HA Ping:', size=(15, 1)), sg.Text('', key='-B_LASTPING_HA-', size=(20, 1))],
    [sg.Text('Last HA Message:', size=(15, 1)), sg.Text('', key='-B_LASTMSG_HA-', size=(20, 1))],
    [sg.Text('Last Z2M Message:', size=(15, 1)), sg.Text('', key='-B_LASTMSG_Z2M-', size=(20, 1))],
    [sg.Text('HA Docker:', size=(15, 1)), sg.Text('', key='-B_HA_DOCKER-', size=(20, 1))],
    [sg.Text('Z2M Docker:', size=(15, 1)), sg.Text('', key='-B_Z2M_DOCKER-', size=(20, 1))],
    [sg.Text('RAID:', size=(15, 1)), sg.Text('', key='-B_RAID-', size=(20, 1))],

    [sg.Button('Restart Homeassistant', key='-RESTART_HA_B-', size=(15, 1))]
]


def top_align_layout(layout):
    """
    Given a layout, return a layout with all rows vertically adjusted to the top

    :param layout: List[List[sg.Element]] The layout to justify
    :return: List[List[sg.Element]]  The new layout that is all top justified
    """
    new_layout = []
    for row in layout:
        new_layout.append(sg.vtop(row))
    return new_layout

# Combine the panels into a layout with columns
layout = [
    [sg.vtop(sg.Column(infra_panel, element_justification='l')),
     sg.vtop(sg.Column(server_a_panel, element_justification='l')),
     sg.vtop(sg.Column(server_b_panel, element_justification='l'))]
]
layout = top_align_layout(layout)

# Create the Window
window = sg.Window('Cluster Control', layout, size=(1024, 600))






def update_label_with_time(label, time, threshold_red, threshold_yellow):
    if time is not None:
        time_difference = datetime.now() - time
        minutes = time_difference.total_seconds() // 60
        if minutes > threshold_red:
            window[label].update("ERR - " + time.strftime('%H:%M:%S'), background_color='red')
        elif minutes > threshold_yellow:
            window[label].update("WARN - " + time.strftime('%H:%M:%S'), background_color='yellow')
        else:
            window[label].update("OK - " + time.strftime('%H:%M:%S'))
    else:
        window[label].update('')

def update_label_with_status(label, time, status):
    if status is not None:
        window[label].update(status, background_color='red')
    else:
        window[label].update('OK - ' + time.strftime('%H:%M:%S'))

if __name__ == '__main__':  
    multiprocessing.freeze_support()
    for process in processes:
        process.start()

    flask_thread.daemon = True
    flask_thread.start()

    # Event Loop to process "events"
    while True:
        event, values = window.read(timeout=100)
        if event == sg.WIN_CLOSED:  # if user closes window
            print("Closing window")
            break

        if not event_queue.empty():
            event = event_queue.get()
            if event['type'] == 'ping_internet' and event['result']:
                update_label_with_time('-INFRA_INTERNET-', event['time'], 5, 1)
            elif event['type'] == 'ping_udm' and event['result']:
                update_label_with_time('-INFRA_ROUTER-', event['time'], 5, 1)
            elif event['type'] == 'ping_main_switch' and event['result']:
                update_label_with_time('-INFRA_SWITCH_MAIN-', event['time'], 5, 1)
            elif event['type'] == 'ping_garden_switch' and event['result']:
                update_label_with_time('-INFRA_SWITCH_GARDEN-', event['time'], 5, 1)
            elif event['type'] == 'ping_backup_switch' and event['result']:
                update_label_with_time('-INFRA_SWITCH_BACKUP-', event['time'], 5, 1)
            elif event['type'] == 'ping_server_a' and event['result']:
                update_label_with_time('-A_LASTPING-', event['time'], 5, 1)
            elif event['type'] == 'ping_server_b' and event['result']:
                update_label_with_time('-B_LASTPING-', event['time'], 5, 1)
            elif event['type'] == 'ping_server_b' and event['result']:
                update_label_with_time('-B_LASTPING-', event['time'], 5, 1)
            elif event['type'] == 'ha_request' and event['result']:
                update_label_with_time('-INFRA_CURRENT_HA-', event['time'], 5, 1)
            elif event['type'] == 'raid_server_a':
                update_label_with_status('-A_RAID-', event['time'], event["result"])
            elif event['type'] == 'raid_server_b':
                update_label_with_status('-B_RAID-', event['time'], event["result"])
            elif event['type'] == 'ha_docker_server_a':
                update_label_with_status('-A_HA_DOCKER-', event['time'], event["result"])
            elif event['type'] == 'z2m_docker_server_a':
                update_label_with_status('-A_Z2M_DOCKER-', event['time'], event["result"])
            elif event['type'] == 'ha_docker_server_b':
                update_label_with_status('-B_HA_DOCKER-', event['time'], event["result"])
            elif event['type'] == 'z2m_docker_server_b':
                update_label_with_status('-B_Z2M_DOCKER-', event['time'], event["result"])

        if "ha_http_server_a" in ping_data:
            update_label_with_time('-A_LASTPING_HA-', ping_data['ha_http_server_a'], 5, 1)
        if "ha_http_server_b" in ping_data:
            update_label_with_time('-B_LASTPIN_HA-', ping_data['ha_http_server_b'], 5, 1)


    print("Closing processes")
    for process in processes:
        process.kill()

    print("Closing window")
    window.close()

    print("Exiting")
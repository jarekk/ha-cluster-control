import PySimpleGUI as sg
from flask import Flask
from datetime import datetime
from threading import Thread
import multiprocessing
import subprocess
import time
import requests
import re
import confirmation_popup
import actions
from raid import check_raid
import configparser
from system_checks import check_docker
from system_checks import check_mac
from system_checks import check_docker_logs
from system_checks import check_http
from system_checks import ping_host
import file_logging
import pytz


app = Flask(__name__)

event_queue = None
def setup_queues():
    global event_queue
    manager = multiprocessing.Manager()
    event_queue = manager.Queue()
    actions.set_event_queue(event_queue, manager)

# Read the configuration file
config = configparser.ConfigParser()
config.read('config.ini')

localtz = pytz.timezone('Europe/Berlin')


# ----------------------------------------------------------------  
# HTTP endpoints
# ----------------------------------------------------------------  

flask_thread = Thread(target=app.run, kwargs={'port':18080})

@app.route('/pingServerA')
def ping_a():
    event_queue.add({"type": "http_ping_received_server_a", "time": datetime.now().astimezone(localtz), "result": True})
    return {'message': 'Server A pinged at {}'.format(datetime.now())}

@app.route('/pingServerB')
def ping_b():
    event_queue.add({"type": "http_ping_received_server_b", "time": datetime.now().astimezone(localtz), "result": True})
    return {'message': 'Server B pinged at {}'.format(datetime.now())}




# ----------------------------------------------------------------  
# Processes
# ----------------------------------------------------------------  

def process_ping(queue, host, label):
    while True:
        result = ping_host(host)
        queue.put({"type": label, "time": datetime.now().astimezone(localtz), "result": result})
        time.sleep(10)

def process_http_check(queue, host, label):
    while True:
        result = check_http(host)
        queue.put({"type": label, "time": datetime.now().astimezone(localtz), "result": result})
        #print(f"HTTP result for {host}: {result}")    

        time.sleep(10)


def process_raid_check(queue, host, label):
    while True:
        result = check_raid(host)
        queue.put({"type": label, "time": datetime.now().astimezone(localtz), "result": result})
        #print(f"RAID result for {host}: {result}")    

        time.sleep(120)

def process_docker_check(queue, host, image, label):
    while True:
        result = check_docker(host, image)
        queue.put({"type": label, "time": datetime.now().astimezone(localtz), "result": result})
        #print(f"Docker result for {host}: {result}")    

        time.sleep(10)

def process_mac_check(queue, host, primary_mac, secondary_mac, label):
    while True:
        result = check_mac(host, primary_mac, secondary_mac)
        queue.put({"type": label, "time": datetime.now().astimezone(localtz), "result": result})
        #print(f"Docker result for {host}: {result}")    

        time.sleep(5)       

def process_check_logs(queue, host, container, label):
    while True:
        result = check_docker_logs(host, container)
        queue.put({"type": label, "time": datetime.now().astimezone(localtz), "result": result})
        #print(f"Docker logs result for {host}: {result}")    

        time.sleep(30)

processes = None
def setup_processes():            
    global processes
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
        multiprocessing.Process(target=process_docker_check, args=(event_queue,config.get('IPs','server_b'),"zigbee2mqtt","z2m_docker_server_b")),
        multiprocessing.Process(target=process_mac_check, args=(event_queue,config.get('IPs','cluster_ip'),config.get('IPs','primary_mac'),config.get('IPs','secondary_mac'), "mac_cluster_id")),
        multiprocessing.Process(target=process_check_logs, args=(event_queue,config.get('IPs','server_a'),"homeassistant","ha_logs_server_a")),
        multiprocessing.Process(target=process_check_logs, args=(event_queue,config.get('IPs','server_b'),"homeassistant","ha_logs_server_b")),
        multiprocessing.Process(target=process_check_logs, args=(event_queue,config.get('IPs','server_a'),"zigbee2mqtt","z2m_logs_server_a")),
        multiprocessing.Process(target=process_check_logs, args=(event_queue,config.get('IPs','server_b'),"zigbee2mqtt","z2m_logs_server_b")),
        multiprocessing.Process(target=actions.action_runner, args=(actions.action_event_queue, event_queue)),
    ]


# ----------------------------------------------------------------
# Evaluate checks
# ----------------------------------------------------------------

last_check_by_type = {}
current_server = None

def evaluate_event_with_time(event, threshold_red, threshold_yellow, secondary):
    if not event["result"]:
        if event["time"] is None:
            event["time"] = datetime.now()

        if secondary is not None and secondary:
            event["status"] = "ERROR_INACTIVE"
        else:
            event["status"] = "ERROR"   
        return event

    time = event["time"]
    if time is not None:
        time_difference = datetime.now().astimezone(localtz) - time
        minutes = time_difference.total_seconds() // 60
        if minutes > threshold_red:
            if secondary is not None and secondary:
                event["status"] = "CRITICAL_INACTIVE"
            else:
                event["status"] = "CRITICAL"
        elif minutes > threshold_yellow:
            if secondary is not None and secondary:
                event["status"] = "WARNING_INACTIVE"
            else:
                event["status"] = "WARNING"
        else:
            event["status"] = "OK" 
    else:
        if secondary is not None and secondary:
            event["status"] = "MISSING_INACTIVE"
        else:
            event["status"] = "MISSING"

    return event

def evaluate_event_with_status(event, secondary):
    if event["result"] is not None:
        if secondary is not None and secondary:
            event["status"] = "CRITICAL_INACTIVE"
        else:
            event["status"] = "CRITICAL"
        
        event["msg"] = event["result"]  
    else:
        event["status"] = "OK"

    return event

def get_gui_label(event):
    if event["type"] in check_configuration:
        c = check_configuration[event["type"]]
        if c is not None and isinstance(c, tuple):
            return c[0]
        else:
            return c
    else:
        return None

def evaluate_check(event, current_server):    
    if event['type'] in ('ping_internet', 'ping_udm', 'ping_main_switch', 'ping_garden_switch', 'ping_backup_switch', 'ping_server_a', 'ping_server_b', 'ha_request'):
        event = evaluate_event_with_time(event, 5, 1, secondary=None)
    elif event['type'] in ('ha_logs_server_a', 'ha_logs_server_b', 'z2m_logs_server_a', 'z2m_logs_server_b', 'http_ping_received_server_a', 'http_ping_received_server_b'):        
        event = evaluate_event_with_time(event, 10, 5, secondary=None if event['type'] in ('ha_logs_server_a', 'z2m_logs_server_a', 'http_ping_received_server_a') else current_server!="secondary")
    elif event['type'] in ('raid_server_a', 'raid_server_b', 'ha_docker_server_a', 'z2m_docker_server_a'):
        event = evaluate_event_with_status(event, secondary=None)
    elif event['type'] in ('ha_docker_server_b', 'z2m_docker_server_b'):
        event = evaluate_event_with_status(event, secondary=current_server!="secondary")   

    elif event['type'] == 'mac_cluster_id':
        event["status"] = "OK"        
      
    elif event['type'] == 'action_result':
        update_last_action(event['result'])

    return event

def evaluate_event_turned_critical(event, last_event):
    if "status" not in event:
        print("Event has no status: ", event)
        return False
    
    if event["status"] in ("CRITICAL", "ERROR") and last_event["status"] not in ("CRITICAL", "ERROR"):
        return True
    return False


def update_event_display(event, window, gui_label):
    if event["type"] in "mac_cluster_id":
        if event["result"] == "primary":
            text = "Primary"
            color = None
        elif event["result"] == "secondary":
            text = "Secondary"
            color = "yellow"
        else:
            text = "Unknown" 
            color = "red"

        window[gui_label].update(text, background_color=color)
        return

    color = None
    if event["status"] in ("CRITICAL"):
        color = "red"
        text = "CRITICAL - " + event["time"].astimezone(localtz).strftime('%H:%M:%S')
    elif event["status"] in ("ERROR"):
        color = "red"
        text = "ERROR - " + event["time"].astimezone(localtz).strftime('%H:%M:%S')
    elif event["status"] in ("MISSING"):
        color = "red"
        text = "CRITICAL - " + event["time"].astimezone(localtz).strftime('%H:%M:%S')
    elif event["status"] in ("WARNING"):
        color = "yellow"
        text = "WARNING - " + event["time"].astimezone(localtz).strftime('%H:%M:%S')
    elif event["status"] in ("ERROR_INACTIVE"):
        text = "Error (but inactive)"
    elif event["status"] in ("CRITICAL_INACTIVE"):
        text = "Critical (but inactive)"
    elif event["status"] in ("WARNING_INACTIVE"):
        text = "Warning (but inactive)"
    elif event["status"] in ("MISSING_INACTIVE"):
        text = "Missing (but inactive)"
    elif event["status"] in ("OK"):
        text = "OK - " + event["time"].astimezone(localtz).strftime('%H:%M:%S')
    else:
        text = "Unknown " + event["status"]

    window[gui_label].update(text, background_color=color)


def process_event(event, window):    
    global current_server
    event = evaluate_check(event, current_server)

    if event["type"] == "mac_cluster_id":
        current_server = event["result"]

    if event["type"] in last_check_by_type and event["status"] != last_check_by_type[event["type"]]["status"]:
        event["changed_state"] = True

    if event["type"] in last_check_by_type and evaluate_event_turned_critical(event, last_check_by_type[event["type"]]):
        event["last_notification"] = datetime.now()
        event["turned_critical"] = True

    if get_gui_label(event):
        update_event_display(event, window, get_gui_label(event))
    else:
        print("No GUI label for event: ", event)
    
    file_logging.log_event(event)

    last_check_by_type[event["type"]] = event


# ----------------------------------------------------------------
# GUI
# ----------------------------------------------------------------

infra_panel = [
    [sg.Text('    Infrastracture', size=(40, 1))],
    [sg.Text('Internet:', size=(15, 1)), sg.Text('', key='-INFRA_INTERNET-', size=(20, 1))],
    [sg.Text('Router:', size=(15, 1)), sg.Text('', key='-INFRA_ROUTER-', size=(20, 1))],
    [sg.Text('Main Switch:', size=(15, 1)), sg.Text('', key='-INFRA_SWITCH_MAIN-', size=(20, 1))],
    [sg.Text('Garden Switch:', size=(15, 1)), sg.Text('', key='-INFRA_SWITCH_GARDEN-', size=(20, 1))],
    [sg.Text('Backup Switch:', size=(15, 1)), sg.Text('', key='-INFRA_SWITCH_BACKUP-', size=(20, 1))],
    [sg.Text('Current HA:', size=(15, 1)), sg.Text('', key='-INFRA_CURRENT_HA-', size=(20, 1))],
    [sg.Text('Active server:', size=(15, 1)), sg.Text('', key='-INFRA_CURRENT_KEEPALIVED-', size=(20, 1))]
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


    [sg.Button('Restart Homeassistant (A)', key='-RESTART_HA_A-', size=(30, 1))],
    [sg.Button('Stop Homeassistant (B)', key='-STOP_HA_A-', size=(30, 1))],
    [sg.Button('Start Homeassistant (C)', key='-START_HA_A-', size=(30, 1))],
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

    [sg.Button('Restart Homeassistant (D)', key='-RESTART_HA_B-', size=(30, 1))],
    [sg.Button('Restart Server (E)', key='-RESTART_SERVER_B-', size=(30, 1))]    
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
     sg.vtop(sg.Column(server_b_panel, element_justification='l'))],
    [sg.Text('Last action: ', size=(15, 1)), sg.Text('', key='-LAST_ACTION-', size=(100, 1))]
]
layout = top_align_layout(layout)

# Create the Window
window = sg.Window('Cluster Control', layout, size=(1280, 1024))


check_configuration = {
    'ping_internet': ('-INFRA_INTERNET-', "Ping to internet"),
    'ping_udm': ('-INFRA_ROUTER-', "Ping to UDM router"),
    'ping_main_switch': ('-INFRA_SWITCH_MAIN-', "Ping to main switch"),
    'ping_garden_switch': ('-INFRA_SWITCH_GARDEN-', "Ping to garden switch"),
    'ping_backup_switch': ('-INFRA_SWITCH_BACKUP-', "Ping to backup switch"),
    'ping_server_a': '-A_LASTPING-',
    'ping_server_b': '-B_LASTPING-',
    'ha_request': '-INFRA_CURRENT_HA-',
    'raid_server_a': '-A_RAID-',
    'raid_server_b': '-B_RAID-',
    'ha_docker_server_a': '-A_HA_DOCKER-',
    'z2m_docker_server_a': '-A_Z2M_DOCKER-',
    'ha_docker_server_b': '-B_HA_DOCKER-',
    'z2m_docker_server_b': '-B_Z2M_DOCKER-',
    'mac_cluster_id': '-INFRA_CURRENT_KEEPALIVED-',
    'ha_logs_server_a': '-A_LASTMSG_HA-',
    'ha_logs_server_b': '-B_LASTMSG_HA-',
    'z2m_logs_server_a': '-A_LASTMSG_Z2M-',
    'z2m_logs_server_b': '-B_LASTMSG_Z2M-',
    'http_ping_received_server_a': '-A_LASTPING_HA-',
    'http_ping_received_server_b': '-B_LASTPING_HA-',
}
    
# ----------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------

def update_label_with_time(label, result, time, threshold_red, threshold_yellow):
    if not result:
        if time is None:
            time = datetime.now()
        window[label].update("ERR - " + time.astimezone(localtz).strftime('%H:%M:%S'), background_color='red')
        return

    if time is not None:
        time_difference = datetime.now().astimezone(localtz) - time
        minutes = time_difference.total_seconds() // 60
        if minutes > threshold_red:
            window[label].update("ERR - " + time.astimezone(localtz).strftime('%H:%M:%S'), background_color='red')
        elif minutes > threshold_yellow:
            window[label].update("WARN - " + time.astimezone(localtz).strftime('%H:%M:%S'), background_color='yellow')
        else:
            window[label].update("OK - " + time.astimezone(localtz).strftime('%H:%M:%S'), background_color=None)
    else:
        window[label].update('Missing', background_color='red')



def update_label_with_time_docker_b_server(label, time, threshold_red, threshold_yellow):
    if time is not None:
        time_difference = datetime.now().astimezone(localtz) - time
        minutes = time_difference.total_seconds() // 60
        if minutes > threshold_red:
            window[label].update("ERR - " + time.astimezone(localtz).strftime('%H:%M:%S'), background_color='red' if current_server == "secondary" else None)
        elif minutes > threshold_yellow:
            window[label].update("WARN - " + time.astimezone(localtz).strftime('%H:%M:%S'), background_color='yellow' if current_server == "secondary" else None)
        else:
            window[label].update("OK - " + time.astimezone(localtz).strftime('%H:%M:%S'))
    else:
        if current_server == "secondary":
            window[label].update('Missing', background_color='red')
        else:
            window[label].update('Missing (but inactive)')


def update_label_with_status(label, time, status):
    if status is not None:
        window[label].update(status, background_color='red')
    else:
        window[label].update('OK - ' + time.astimezone(localtz).strftime('%H:%M:%S'))

def update_label_with_status_docker(label, time, status):
    if status is not None:
        window[label].update(status, background_color='red')
    else:
        window[label].update('UP - ' + time.astimezone(localtz).strftime('%H:%M:%S'))

def update_label_with_status_docker_b_server(label, time, status, current_server):
    if status is not None:
        if current_server == "secondary":
            window[label].update(status, background_color='red')
        else:
            window[label].update(status + " (but inactive)", background_color=None)
    else:
        window[label].update('UP - ' + time.astimezone(localtz).strftime('%H:%M:%S'))

def update_last_action(text):
    window['-LAST_ACTION-'].update(text + " - " + datetime.now().astimezone(localtz).strftime('%H:%M:%S'))

if __name__ == '__main__':  
    multiprocessing.freeze_support()
    setup_queues()
    setup_processes()
    for process in processes:
        process.start()

    flask_thread.daemon = True
    flask_thread.start()

    window.finalize()
    window.bind("E", "-RESTART_SERVER_B-")


    # Event Loop to process "events"
    while True:
        event, values = window.read(timeout=100)
        if event == sg.WIN_CLOSED:  # if user closes window
            print("Closing window")
            break
        if event.startswith('-RESTART_HA_A-'):
            # Handle the button press for restarting Homeassistant on Server A
            # Add your code here
            print("Restarting Homeassistant on Server A")
        elif event.startswith('-STOP_HA_A-'):
            # Handle the button press for stopping Homeassistant on Server A
            # Add your code here
            print("Restarting Homeassistant on Server A")
        elif event.startswith('-START_HA_A-'):
            # Handle the button press for starting Homeassistant on Server A
            # Add your code here
            print("Restarting Homeassistant on Server A")
        elif event.startswith('-RESTART_HA_B-'):
            # Handle the button press for restarting Homeassistant on Server B
            # Add your code here
            print("Restarting Homeassistant on Server A")
        elif event.startswith('-RESTART_SERVER_B-'):
            if confirmation_popup.show_popup("restart Server B"):
                update_last_action("Restarting Server B")
                actions.invoke_action({"type": "restart_server", "ip": config.get('IPs','server_b')})
       
        if not event_queue.empty():
            process_event(event_queue.get(), window)    


    print("Closing processes")
    for process in processes:
        process.kill()

    print("Closing window")
    window.close()

    print("Exiting")
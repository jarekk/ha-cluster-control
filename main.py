import FreeSimpleGUI as sg
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
from system_checks import check_victronmetrics
import internet
import file_logging
import pytz
import gsm


NONE_COLOR = "#64778d"

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


device = config.get("GSM", "device") if config.has_option("GSM", "device") else None
gsm = gsm.Gsm(config.get("GSM", "pin"), config.get("GSM", "recipient"), device)

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

def process_check_victronmetrics(queue, host, label):
    while True:
        result = check_victronmetrics(host)
        queue.put({"type": label, "time": datetime.now().astimezone(localtz), "result": result is not None, "metrics": result})

        time.sleep(5)

def process_check_gsm(queue, label):
    time.sleep(15)
    while True:
        result = gsm.get_status()            
        queue.put({"type": label, "time": datetime.now().astimezone(localtz), "result": result})

        time.sleep(5)

def process_internet_check(queue):
    time.sleep(3)
    backup_count = 0
    while True:
        result = internet.check_backup_internet()
        if "BACKUP" in result:
            backup_count+=1            
        else:
            backup_count = 0

        queue.put({"type": "internet", "time": datetime.now().astimezone(localtz), "result": result, "backup_count": backup_count})

        now = datetime.now().astimezone(localtz)
        if backup_count>=3 and result == "BACKUP_PASS_INACTIVE" and not (0 <= now.hour < 6 or (now.hour == 6 and now.minute < 30)):            
            result = internet.book_internet_pass()
            queue.put({"type": "internet-purchase", "time": datetime.now().astimezone(localtz), "result": result})      

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
        multiprocessing.Process(target=process_check_victronmetrics, args=(event_queue,config.get('IPs','victron'),"victron_metrics")),
        multiprocessing.Process(target=process_internet_check, args=(event_queue,)),
        multiprocessing.Process(target=actions.action_runner, args=(actions.action_event_queue, event_queue)),
    ]

threads = None
def setup_threads():
    global threads
    threads =  [
        Thread(target=process_check_gsm, args=(event_queue, "gsm_status"), daemon=True),
    ]


# ----------------------------------------------------------------
# Evaluate checks
# ----------------------------------------------------------------

last_check_by_type = {}
current_server = None
event_last_success = {}

def evaluate_event_with_time(event, threshold_red, threshold_yellow, secondary):
    if not event["result"]:
        if event["time"] is None:
            event["time"] = datetime.now()

        if event["type"] in event_last_success:
            time = event_last_success[event["type"]] 
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
            event_last_success[event["type"]] = time
    else:
        if secondary is not None and secondary:
            event["status"] = "MISSING_INACTIVE"
        else:
            event["status"] = "MISSING"

    return event

event_count_failures = {}

def evaluate_event_with_status(event, secondary, critical_treshold):
    if event["result"] is not None:

        if event["type"] in event_count_failures:
            event_count_failures[event["type"]] += 1
        else:
            event_count_failures[event["type"]] = 1

        if event_count_failures[event["type"]] > critical_treshold:
            if secondary is not None and secondary:
                event["status"] = "CRITICAL_INACTIVE"
            else:
                event["status"] = "CRITICAL"
        else:
            event["status"] = "OK"
        
        event["msg"] = event["result"]  
    else:
        event["status"] = "OK"
        event_count_failures[event["type"]] = 0

    return event

def evaluate_victron(event):
    if event["result"]:
        metrics = event["metrics"]
        if metrics:
            event["mains"] = metrics["led_map"]["led_mains"] == "dot-green"
            event["inverter"] = metrics["led_map"]["led_inverter"] == "dot-green"  

            if not event["mains"]:
                text = 'CRITICAL - Power fail (' + metrics["battery_charge"] + '}%)'
                event["status"] = "CRITICAL"
            else:
                text = "OK (" + metrics['battery_charge'] + "%)"
                event["status"] = "OK"

            event["msg"] = text
        else:
            event["status"] = "MISSING"
            event["msg"] = "MISSING - No metrics"
    else:
        event["status"] = "MISSING"
        event["msg"] = "MISSING - Cannot fetch"

    #print ("Victron event: ", event)
    return event

def evaluate_gsm(event):
    print("GSM event: ", event)
    if event["result"]["signal"] > 0:
        event["status"] = "OK"
        event["msg"] = "OK - signal: " + str(event["result"]["signal"]) + "%, network: " + event["result"]["network"]
    else:
        event["status"] = "CRITICAL"        
        event["msg"] = "CRITICAL, no signal"
        
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
    
def get_notification_label(event):
    if event["type"] in check_configuration:
        c = check_configuration[event["type"]]
        if c is not None and isinstance(c, tuple):
            return c[1]
        else:
            return c
    else:
        return None

def evaluate_check(event, current_server):    
    if event['type'] in ('ping_internet', 'ping_udm', 'ping_main_switch', 'ping_garden_switch', 'ping_backup_switch', 'ping_server_a', 'ping_server_b', 'ha_request'):
        event = evaluate_event_with_time(event, 6, 3, secondary=None)
    elif event['type'] in ('ha_logs_server_a', 'ha_logs_server_b', 'z2m_logs_server_a', 'z2m_logs_server_b', 'http_ping_received_server_a', 'http_ping_received_server_b'):        
        event = evaluate_event_with_time(event, 10, 5, secondary=None if event['type'] in ('ha_logs_server_a', 'z2m_logs_server_a', 'http_ping_received_server_a') else current_server!="secondary")
    elif event['type'] in ('raid_server_a', 'raid_server_b', 'ha_docker_server_a', 'z2m_docker_server_a'):
        event = evaluate_event_with_status(event, secondary=None, critical_treshold=5)
    elif event['type'] in ('ha_docker_server_b', 'z2m_docker_server_b'):
        event = evaluate_event_with_status(event, secondary=current_server!="secondary", critical_treshold=5)   
    elif event['type'] == 'mac_cluster_id':
        event["status"] = "OK"        
    elif event['type'] == 'victron_metrics':
        event = evaluate_victron(event)
    elif event['type'] == 'gsm_status':
        event = evaluate_gsm(event)
    elif event['type'] == 'action_result':
        event["status"] = "NONE"
    elif event['type'] == 'internet':
        if "PRIMARY" in event["result"]:
            event["status"] = "OK"
            event["msg"] = "OK - Primary internet"
        else:
            event["status"] = "CRITICAL"
            event["msg"] = "CRITICAL - LTE internet"
    elif event['type'] == 'internet-purchase':                
        event["status"] = "OK"

    return event

def evaluate_event_turned_critical(event, last_event):
    if "status" not in event:
        print("Event has no status: ", event)
        return False
    
    if event["status"] in ("CRITICAL", "ERROR") and last_event["status"] not in ("CRITICAL", "ERROR"):
        return True
    return False


def update_event_display(event, window, gui_label):
    if event["type"] == "gsm_status":
        window[gui_label].update(event["msg"], background_color="red" if event["status"] == "CRITICAL" else None)
        return

    if event["type"] == "victron_metrics":
        if event["status"] == "OK":
            text = event["msg"]
            color = NONE_COLOR
        elif event["status"] in ("CRITICAL", "MISSING"):
            text = event["msg"]            
            color = "red"

        window[gui_label].update(text, background_color=color)
        return

    if event["type"] in "mac_cluster_id":
        if event["result"] == "primary":
            text = "Primary"
            color = NONE_COLOR
        elif event["result"] == "secondary":
            text = "Secondary"
            color = "yellow"
        else:
            text = "Unknown" 
            color = "red"

        window[gui_label].update(text, background_color=color)
        return



    color = NONE_COLOR
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

def notify_event(event, last_event):
    if ("changed_state" in event and event["changed_state"]) or (event["type"] in ("action_invoked","action_result")):
        if event["type"]=='action_invoked':
            text = event["time"].astimezone(localtz).strftime('%d-%m %H:%M:%S: ') + event["result"]
        elif event["type"]=='action_result':
            text = event["time"].astimezone(localtz).strftime('%d-%m %H:%M:%S: ') + "Action finished: " + event["result"]
        else:
            text = event["time"].astimezone(localtz).strftime('%d-%m %H:%M:%S: ') + get_notification_label(event) + " changed to " + event["status"]
        gsm.send_sms(text)
        window['-NOTIFICATIONS-'].print(text)


def process_event(event, window):    
    global current_server
    event = evaluate_check(event, current_server)

    if event["type"] == "mac_cluster_id":
        current_server = event["result"]

    if event["type"] in last_check_by_type and event["status"] != last_check_by_type[event["type"]]["status"]:
        event["changed_state"] = True

    if event["type"] in last_check_by_type and evaluate_event_turned_critical(event, last_check_by_type[event["type"]]):
        event["turned_critical"] = True


    if event["type"] == "internet-purchase":
        text="Internet backup purchased: " + event["result"]
        gsm.send_sms(text)
        window['-NOTIFICATIONS-'].print(text) 
    else:
        notify_event(event, last_check_by_type[event["type"]] if event["type"] in last_check_by_type else None) 

    if get_gui_label(event):
        update_event_display(event, window, get_gui_label(event))
    else:
        if event["type"] not in ("internet-purchase"):
            print("No GUI label for event: ", event)
    
    #file_logging.log_event(event)

    last_check_by_type[event["type"]] = event


# ----------------------------------------------------------------
# GUI
# ----------------------------------------------------------------

infra_panel = [
    [sg.Text('    Infrastructure', size=(40, 1))],
    [sg.Text('Internet:', size=(15, 1)), sg.Text('', key='-INFRA_INTERNET-', size=(25, 1))],
    [sg.Text('Internet Provider:', size=(15, 1)), sg.Text('', key='-INFRA_INTERNET_PROVIDER-', size=(25, 1))],
    [sg.Text('Router:', size=(15, 1)), sg.Text('', key='-INFRA_ROUTER-', size=(20, 1))],
    [sg.Text('Main Switch:', size=(15, 1)), sg.Text('', key='-INFRA_SWITCH_MAIN-', size=(20, 1))],
    [sg.Text('Garden Switch:', size=(15, 1)), sg.Text('', key='-INFRA_SWITCH_GARDEN-', size=(20, 1))],
    [sg.Text('Backup Switch:', size=(15, 1)), sg.Text('', key='-INFRA_SWITCH_BACKUP-', size=(20, 1))],
    [sg.Text('Current HA:', size=(15, 1)), sg.Text('', key='-INFRA_CURRENT_HA-', size=(20, 1))],
    [sg.Text('Active server:', size=(15, 1)), sg.Text('', key='-INFRA_CURRENT_KEEPALIVED-', size=(20, 1))],
    [sg.Text('UPS:', size=(15, 1)), sg.Text('', key='-VICTRON_METRICS-', size=(25, 1))],
    [sg.Text('GSM:', size=(15, 1)), sg.Text('', key='-GSM_STATUS-', size=(25, 1))],

    [sg.Button('Restart Cable Modem (T)', key='-RESTART_MODEM-', size=(30, 1))],

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
    [sg.Button('Restart Z2M (D)', key='-RESTART_Z2M_A-', size=(30, 1))],
    [sg.Button('Stop Z2M (E)', key='-STOP_Z2M_A-', size=(30, 1))],
    [sg.Button('Start Z2M (F)', key='-START_Z2M_A-', size=(30, 1))],
    [sg.Button('Restart server (G)', key='-RESTART_SERVER_A-', size=(30, 1))],
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

    [sg.Button('Restart Homeassistant (J)', key='-RESTART_HA_B-', size=(30, 1))],
    [sg.Button('Stop Homeassistant (K)', key='-STOP_HA_B-', size=(30, 1))],
    [sg.Button('Start Homeassistant (L)', key='-START_HA_B-', size=(30, 1))],
    [sg.Button('Restart Z2M (M)', key='-RESTART_Z2M_B-', size=(30, 1))],
    [sg.Button('Stop Z2M (N)', key='-STOP_Z2M_A-', size=(30, 1))],
    [sg.Button('Start Z2M (O)', key='-START_Z2M_A-', size=(30, 1))],
    [sg.Button('Restart server (P)', key='-RESTART_SERVER_B-', size=(30, 1))],
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
    [sg.Multiline(key='-NOTIFICATIONS-', size=(200, 20), background_color=NONE_COLOR, text_color="white")]
]
layout = top_align_layout(layout)

# Create the Window
window = sg.Window('Cluster Control', layout, size=(1280, 1024))

button_mapping = {
    '-RESTART_MODEM-': ('T', "Restart internet modem", ("restart_modem", "")),
    
    '-RESTART_HA_A-': ('A', "Restart Homeassistant on server A", ("restart_ha", config.get('IPs','server_a'))),
    '-STOP_HA_A-': ('B', "Stop Homeassistant on server A", ("stop_ha", config.get('IPs','server_a'))),
    '-START_HA_A-': ('C', "Start Homeassistant on server A", ("start_ha", config.get('IPs','server_a'))),
    '-RESTART_Z2M_A-': ('D', "Restart Z2M on server A", ("restart_z2m", config.get('IPs','server_a'))),
    '-STOP_Z2M_A-': ('H', "Stop Z2M on server A", ("stop_z2m", config.get('IPs','server_a'))),
    '-START_Z2M_A-': ('F', "Start Z2M on server A", ("start_z2m", config.get('IPs','server_a'))),
    '-RESTART_SERVER_A-': ('G', "Restart server A", ("restart_server", config.get('IPs','server_a'))),
    
    '-RESTART_HA_B-': ('J', "Restart Homeassistant on server B",  ("restart_ha", config.get('IPs','server_b'))),
    '-STOP_HA_B-': ('K', "Stop Homeassistant on server B", ("stop_ha", config.get('IPs','server_b'))),
    '-START_HA_B-': ('L', "Start Homeassistant on server B", ("start_ha", config.get('IPs','server_b'))),
    '-RESTART_Z2M_B-': ('M', "Restart Z2M on server B", ("restart_z2m", config.get('IPs','server_b'))),
    '-STOP_Z2M_B-': ('N', "Stop Z2M on server B", ("stop_z2m", config.get('IPs','server_b'))),
    '-START_Z2M_B-': ('O', "Start Z2M on server B", ("start_z2m", config.get('IPs','server_b'))),
    '-RESTART_SERVER_B-': ('P', "Restart server B", ("restart_server", config.get('IPs','server_b'))),
}


check_configuration = {
    'ping_internet': ('-INFRA_INTERNET-', "Ping to internet"),
    'ping_udm': ('-INFRA_ROUTER-', "Ping to UDM router"),
    'ping_main_switch': ('-INFRA_SWITCH_MAIN-', "Ping to main switch"),
    'ping_garden_switch': ('-INFRA_SWITCH_GARDEN-', "Ping to garden switch"),
    'ping_backup_switch': ('-INFRA_SWITCH_BACKUP-', "Ping to backup switch"),
    'ping_server_a': ('-A_LASTPING-', "Ping to server A"),
    'ping_server_b': ('-B_LASTPING-', "Ping to server B"),
    'ha_request': ('-INFRA_CURRENT_HA-', "Current HA"),
    'raid_server_a': ('-A_RAID-', "RAID on server A"),
    'raid_server_b': ('-B_RAID-', "RAID on server B"),
    'ha_docker_server_a': ('-A_HA_DOCKER-', "HA Docker on server A"),
    'z2m_docker_server_a': ('-A_Z2M_DOCKER-', "Z2M Docker on server A"),
    'ha_docker_server_b': ('-B_HA_DOCKER-', "HA Docker on server B"),
    'z2m_docker_server_b': ('-B_Z2M_DOCKER-', "Z2M Docker on server B"),
    'mac_cluster_id': ('-INFRA_CURRENT_KEEPALIVED-', "Current cluster IP"),
    'ha_logs_server_a': ('-A_LASTMSG_HA-', "HA logs on server A"),
    'ha_logs_server_b': ('-B_LASTMSG_HA-', "HA logs on server B"),
    'z2m_logs_server_a': ('-A_LASTMSG_Z2M-', "Z2M logs on server A"),
    'z2m_logs_server_b': ('-B_LASTMSG_Z2M-', "Z2M logs on server B"),
    'http_ping_received_server_a': '-A_LASTPING_HA-',
    'http_ping_received_server_b': '-B_LASTPING_HA-',
    'victron_metrics': ('-VICTRON_METRICS-', "UPS"),
    'gsm_status': ('-GSM_STATUS-', "GSM"),
    'internet' : ('-INFRA_INTERNET_PROVIDER-', "Internet provider"),    
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

if __name__ == '__main__':  
    multiprocessing.freeze_support()
    setup_queues()
    setup_processes()
    setup_threads()

    for process in processes:
        process.start()
    for t in threads:
        t.start()

    flask_thread.daemon = True
    flask_thread.start()

    gsm.start()

    window.finalize()
    for k in button_mapping:        
        window.bind(button_mapping[k][0], k)
    window.bind("X", "-CLOSE-")
 
    # Event Loop to process "events"
    while True:
        event, values = window.read(timeout=100)
        if event == sg.WIN_CLOSED or event=='-CLOSE-':  # if user closes window
            print("Closing window")
            break

        if event in button_mapping:
            if confirmation_popup.show_popup(button_mapping[event][1]):
                notify_event({"type": "action_invoked", "time":  datetime.now().astimezone(localtz), "result": "Action started: " + button_mapping[event][1]}, None)
                actions.invoke_action(button_mapping[event][2])

        if not event_queue.empty():
            process_event(event_queue.get(), window)    


    print("Closing processes")
    for process in processes:
        process.kill()

    print("Closing window")
    window.close()

    print("Exiting")
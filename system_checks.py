import json
import subprocess
import re
from datetime import datetime
import pytz
import requests
import websocket
import json


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
                


def check_docker(host, image):
    try:
        output = subprocess.check_output(['ssh', host, 'sudo docker ps --format "{{json .}}"']).decode("utf-8")
        
        #print("Docker output: ", output)
        for line in output.splitlines():
            try:
                container_info = json.loads(line)
                container_status = container_info['Status']
                container_image = container_info['Image']
                if image in container_image and "Up" in container_status:
                    return None
                
            except json.JSONDecodeError:
                continue

        return "No container"
    
    except subprocess.CalledProcessError:
        return "Check failed"

def check_mac(ip, primary, secondary):
    try:
        # Ping the IP to ensure it's in the ARP table
        subprocess.run(['ping', '-c', '1', ip], stdout=subprocess.DEVNULL)

        # Get the ARP table entry
        arp_output = subprocess.check_output(['arp', '-n', ip]).decode()

        #print ("ARP output: ", arp_output, " primary: ", primary, " secondary: ", secondary)

        # Extract the MAC address
        for line in arp_output.split('\n'):
            if ip in line:
                if primary in line:                    
                    return "primary"
                elif secondary in line:
                    return "secondary"
    except Exception as e:
        print(f"Error: {e}")

    return None


def check_docker_logs(host, container):
    try:
        output = subprocess.check_output(['ssh', host, f'sudo docker logs -n 10 {container}'], stderr=subprocess.STDOUT).decode("utf-8")

        #print("For host XX", host , "and container", container," docker logs: ", output)
        # Extract the date and time from the last log line
        last_log_line = output.splitlines()[-1]
        #print("Last log line: ", last_log_line)

        datetime_match = re.search(r'^.{1,10}?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', last_log_line)
        if datetime_match:
            dt = datetime_match.group(1)
            #print("Datetime: ", dt)

            local_timezone = pytz.timezone('Europe/Berlin')
            utc_timezone = pytz.timezone('UTC')
            last_log_datetime = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
            #print("Last log datetime: ", str(last_log_datetime))
            if container == "homeassistant":
                last_log_datetime = last_log_datetime.replace(tzinfo=utc_timezone)
            else:
                last_log_datetime = last_log_datetime.replace(tzinfo=local_timezone)
            return last_log_datetime
    except subprocess.CalledProcessError:
        pass
    except Exception as e:
        print(f"Error: {e}")
    
    return None


def check_victronmetrics(host):
    try:
        ws = websocket.create_connection(f"ws://{host}:8080/ws")
        request = {
            "type": "get_metrics"
        }
        ws.send(json.dumps(request))

        response = ws.recv()
        #print("victron response: ", response)

        ws.close()
        return json.loads(response)

    except Exception as e:
        print(f"Victron Error: {e}")
        return None

def parse_metrics(text):
    ALLOWED_METRICS = {
        'battery_charge_percentage',
        'battery_current_a',
        'battery_power_w',
        'battery_voltage_v',
        'mains_current_in_a',
        'mains_current_out_a',
        'mains_freq_in_hz',
        'mains_freq_out_hz',
        'mains_power_in_va',
        'mains_power_out_va',
        'mains_voltage_in_v',
        'mains_voltage_out_v'
    }
    metrics = {}
    lines = text.split('\n')
    for line in lines:
        if line.startswith('# HELP'):
            pass
        elif line.startswith('# TYPE'):
            pass
        elif line != '':
            parts = line.split(' ')
            metric_name = parts[0]
            metric_value = parts[1]
            if metric_name in ALLOWED_METRICS:
                metrics[metric_name][parts[0]] = metric_value

    return metrics

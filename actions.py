import subprocess
import threading
import time
import multiprocessing
from datetime import datetime
import pytz

action_event_queue = None
event_queue = None


localtz = pytz.timezone('Europe/Berlin')


def set_event_queue(queue, manager):
    global event_queue
    global action_event_queue
    event_queue = queue
    action_event_queue = manager.Queue()

def invoke_action(action):
    action_event_queue.put({"type": action[0], "ip": action[1]})

def action_runner(action_event_queue, event_queue):
    while True:
        event = action_event_queue.get()
        print("Action runner got event: ", event)
        perform_action(event, event_queue)        

def perform_action(action, event_queue):
    if action["type"] == "restart_server":
        res = execute_remote_command(action["ip"], "sudo reboot", "restarting server")
        event_queue.put({"type": "action_result", "result": res, "time": datetime.now().astimezone(localtz)})
    elif action["type"] == "restart_modem":
        pass
    elif action["type"] == "restart_ha":
        res = execute_remote_command(action["ip"], "cd /opt; sudo docker compose -f /opt/docker-compose.yaml restart homeassistant", "restart homeassistant")
        event_queue.put({"type": "action_result", "result": res, "time": datetime.now().astimezone(localtz)})        
    elif action["type"] == "start_ha":
        res = execute_remote_command(action["ip"], "cd /opt; sudo docker compose -f /opt/docker-compose.yaml start homeassistant", "start homeassistant")
        event_queue.put({"type": "action_result", "result": res, "time": datetime.now().astimezone(localtz)})
    elif action["type"] == "stop_ha":
        res = execute_remote_command(action["ip"], "cd /opt; sudo docker compose -f /opt/docker-compose.yaml stop homeassistant", "stop homeassistant")
        event_queue.put({"type": "action_result", "result": res, "time": datetime.now().astimezone(localtz)})
    elif action["type"] == "restart_z2m":
        res = execute_remote_command(action["ip"], "cd /opt; sudo docker compose -f /opt/docker-compose.yaml restart zigbee2mqtt", "restart zigbee2mqtt")
        event_queue.put({"type": "action_result", "result": res, "time": datetime.now().astimezone(localtz)})        
    elif action["type"] == "start_z2m":
        res = execute_remote_command(action["ip"], "cd /opt; sudo docker compose -f /opt/docker-compose.yaml start zigbee2mqtt", "start zigbee2mqtt")
        event_queue.put({"type": "action_result", "result": res, "time": datetime.now().astimezone(localtz)})
    elif action["type"] == "stop_z2m":
        res = execute_remote_command(action["ip"], "cd /opt; sudo docker compose -f /opt/docker-compose.yaml stop zigbee2mqtt", "stop zigbee2mqtt")
        event_queue.put({"type": "action_result", "result": res, "time": datetime.now().astimezone(localtz)})

def execute_remote_command(ip, cmd, action):
    try:
        print("Trying to restart server at IP: ", ip)
        process = subprocess.Popen(['ssh', ip, cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        timer = threading.Timer(10, process.kill)
        timer.start()
        output, _ = process.communicate()
        return_code = process.returncode
        timer.cancel()

        if return_code != 0:
            print("Error while '" + action + "', output: ", output)
            return "Error while '" + action + "': " + output.decode("utf-8")
        else:
            print("Successful '" + action + "', output: ", output)
            return "Successful '" + action + "': " + output.decode("utf-8")
    except Exception as e:
        print("Error while '" + action + "': ", e)
        return "Error while '" + action + "': " + e
import subprocess
import threading
import time
import multiprocessing

action_event_queue = None
event_queue = None

def set_event_queue(queue, manager):
    global event_queue
    global action_event_queue
    event_queue = queue
    action_event_queue = manager.Queue()

def invoke_action(action):
    action_event_queue.put(action)

def action_runner(action_event_queue, event_queue):
    while True:
        event = action_event_queue.get()
        print("Action runner got event: ", event)
        perform_action(event, event_queue)        

def perform_action(action, event_queue):
    if action["type"] == "restart_server":
        res = restart_server(action["ip"])
        event_queue.put({"type": "action_result", "result": res})

def restart_server(ip):
    try:
        print("Trying to restart server at IP: ", ip)
        process = subprocess.Popen(['ssh', ip, 'sudo reboot'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        timer = threading.Timer(10, process.kill)
        timer.start()
        output, _ = process.communicate()
        return_code = process.returncode
        timer.cancel()

        if return_code != 0:
            print("Error restarting server, output: ", output)
            return "Error restarting server: " + output.decode("utf-8")
        else:
            print("Restarted server, output: ", output)
            return "Server restarted: " + output.decode("utf-8")
    except Exception as e:
        print("Error restarting server: ", e)
        return "Restarting server, error: {e}"
import subprocess
import re

def parse_controller_status(output):
    match = re.search(r"Controller Status\s+:\s+(\w+)", output)
    if match:
        return match.group(1)
    return None

def parse_logical_device_status(output):
    matches = re.findall(r"Logical device number (\d+)\n\s+Logical device name\s+:\s+(\w+)\n\s+(?:[\w\s]+\s+:\s+[\d\w]+\n)+\s+Status of logical device\s+:\s+(\w+)", output)
    return {int(number): {"name": name, "status": status} for number, name, status in matches}

def parse_physical_device_state(output):
    matches = re.findall(r"Device #(\d+)\n\s+Device is a Hard drive\n\s+State\s+:\s+(\w+)", output)
    return {int(number): state for number, state in matches}

def parse_physical_device_smart_status(output):
    matches = re.findall(r"Device #(\d+)\n\s+Device is a Hard drive\n(?:\s+.+\s+:\s+.+\n)+?\s+S.M.A.R.T.\s+:\s+(\w+)", output)
    return {int(number): status for number, status in matches}



def check_raid(host):
    try:
        output = subprocess.check_output(['ssh', host, 'arcconf getconfig 1']).decode("utf-8")
        #print("SSH finished, output is", output)

        controller_status = parse_controller_status(output)
        logical_device_status = parse_logical_device_status(output)
        physical_device_state = parse_physical_device_state(output)
        physical_device_smart_status = parse_physical_device_smart_status(output)

        # Print debug information
        #print("Controller Status:", controller_status)
        #print("Logical Device Status:", logical_device_status)
        #print("Physical Device State:", physical_device_state)
        #print("Physical Device SMART Status:", physical_device_smart_status)


        if controller_status != "Optimal":
            return "Controller error"
        
        if len(logical_device_status) == 0:
            return "No logical devices found"

        for number, device in logical_device_status.items():
            if device["status"] != "Optimal":
                return f"Logical device {number} error: {device['status']}"
        
        for number, state in physical_device_state.items():
            if state != "Online":
                return f"Physical device {number} error: {state}"
            
        for number, status in physical_device_smart_status.items():
            if status != "No":
                return f"Physical device {number} error: S.M.A.R.T. status is {status}"
            
        return None

    except subprocess.CalledProcessError as e:
        print("Error while running arcconf, exception is", e)
        return "Error checking status"
    
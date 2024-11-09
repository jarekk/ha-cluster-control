import json
import subprocess


def check_docker(host, image):
    try:
        output = subprocess.check_output(['ssh', host, 'sudo docker ps --format "{{json .}}"']).decode("utf-8")
        
        print("Docker output: ", output)
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


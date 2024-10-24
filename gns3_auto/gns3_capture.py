import os
import json
import time
import sys
import signal

import requests
import gns3fy
from netmiko import Netmiko

SERVER_IP = "127.0.0.1"
SERVER_PORT = 8080
SERVER_URL = f"http://{SERVER_IP}:{SERVER_PORT}"


def signal_handler(signum, frame):
    stopCaptureAllLinks(lab)
    downloadPcaps(lab)
    sys.exit(0)


def startAllNodes(lab):
    for node in lab.nodes:
        if node.status == 'stopped':
            print(f"Start node {node.name}")
            node.start()
    # Should wait after gns3_deploy_topology.py
    print("Wait 30 seconds for startup ...")
    time.sleep(30)


def stopAllNodes(lab):
    for node in lab.nodes:
        node.stop()


def setLinkFilters(lab):
    for link in lab.links:
        link.update(**{"filters": {"delay": [25, 0]}})
        # print(link.filters)


def startCaptureAllLinks(lab):
    captures = {}
    for link in lab.links:
        res = requests.post(
            f"{SERVER_URL}/v2/projects/{lab.project_id}/links/{link.link_id}/start_capture")
        if res.ok:
            captures[link.link_id] = res.json()
        else:
            print(res.status_code, res.text)

    output_dir = f"./output/{lab.name}"
    os.makedirs(output_dir, exist_ok=True)
    with open(f"{output_dir}/captures.json", "w") as fout:
        fout.write(json.dumps(captures))

    print("Start capturing all links...")
    return captures


def stopCaptureAllLinks(lab):
    for link in lab.links:
        res = requests.post(
            f"{SERVER_URL}/v2/projects/{lab.project_id}/links/{link.link_id}/stop_capture")
        if not res.ok:
            print(res.status_code, res.text)
    print("Stopped capturing all links.")


def run_cmd(cmd):
    from subprocess import Popen, PIPE
    std_out, std_err = Popen(
        cmd, shell=True, stdout=PIPE, stderr=PIPE).communicate()
    return std_out.decode().strip()


def mergePcaps(dirt, pcaps):
    cwd = os.getcwd()
    os.chdir(dirt)
    cmd = "mergecap -w merged.pcap %s" % (" ".join(pcaps))
    run_cmd(cmd)
    os.chdir(cwd)


def downloadPcaps(lab, captures=None):
    output_dir = f"./output/{lab.name}"
    os.makedirs(output_dir, exist_ok=True)

    if captures is None:
        with open(f"{output_dir}/captures.json", "r") as fin:
            captures = json.loads(fin.read())

    pcaps = []
    for link_id in captures:
        capture = captures[link_id]
        file_name = capture["capture_file_name"]
        file_path = f"v2/projects/{lab.project_id}" + \
            f"/files/project-files/captures/{file_name}"
        res = requests.get(f"{SERVER_URL}/{file_path}")
        if res.ok:
            with open(f"{output_dir}/{file_name}", 'wb') as fd:
                for chunk in res.iter_content(chunk_size=256*1024):
                    fd.write(chunk)
            pcaps.append(file_name)
            print(f"Downloaded {file_path}")
        else:
            print(file_path, res.status_code)
    mergePcaps(output_dir, pcaps)


def getNodeByName(name):
    for node in lab.nodes:
        if node.name == 'R1':
            return node


def announcePrefix(lab):
    cmds = ["router bgp 1", "network 1.127.0.1 mask 255.255.255.255"]
    device = {
        "host": SERVER_IP,
        "port": getNodeByName("R1").console,
        "device_type": 'cisco_ios_telnet',
        "global_delay_factor": 3,
        "global_cmd_verify": False
    }
    net_connect = Netmiko(**device)
    net_connect.enable()
    net_connect.send_config_set(cmds, cmd_verify=False)
    net_connect.disconnect()


if __name__ == "__main__":
    global lab
    print(sys.argv[1], SERVER_URL)
    gns3_server = gns3fy.Gns3Connector(SERVER_URL)
    lab = gns3fy.Project(name=sys.argv[1], connector=gns3_server)
    lab.get()

    lab.open()
    print(lab.status)
    print(lab.stats)
    signal.signal(signal.SIGINT, signal_handler)
    print(f"Wait for opening project..")
    time.sleep(10)

    setLinkFilters(lab)
    startAllNodes(lab)
    captures = startCaptureAllLinks(lab)
    announcePrefix(lab)

    print(f"Wait for 240 seconds...")
    time.sleep(240)

    stopCaptureAllLinks(lab)
    downloadPcaps(lab)
    stopAllNodes(lab)

    # lab.close()

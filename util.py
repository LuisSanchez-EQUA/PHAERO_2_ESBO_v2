"""
______ ____  _    _           _____ _____             _____ _____ ______
|  ____/ __ \| |  | |  /\     |_   _|  __ \   /\      |_   _/ ____|  ____|
| |__ | |  | | |  | | /  \      | | | |  | | /  \       | || |    | |__
|  __|| |  | | |  | |/ /\ \     | | | |  | |/ /\ \      | || |    |  __|
| |___| |__| | |__| / ____ \   _| |_| |__| / ____ \    _| || |____| |____
|______\___\_\\____/_/    \_\ |_____|_____/_/    \_\  |_____\_____|______|
https://equa.se/en/

"""

import ctypes
import json
import time
import subprocess
import os

from phase0.paths import IDA_ICE_BIN

path_to_ice = str(IDA_ICE_BIN) + "\\"
process = None
pid = None
ida_lib = None


def _configure_ida_lib() -> None:
    global ida_lib
    ida_lib.connect_to_ida.restype = ctypes.c_bool
    ida_lib.connect_to_ida.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    ida_lib.switch_remote_connection.restype = ctypes.c_bool
    ida_lib.switch_remote_connection.argtypes = [ctypes.c_char_p]
    ida_lib.switch_api_version.restype = ctypes.c_bool
    ida_lib.switch_api_version.argtypes = [ctypes.c_long]
    ida_lib.call_ida_function.restype = ctypes.c_long
    ida_lib.call_ida_function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.ida_disconnect.restype = ctypes.c_bool
    ida_lib.ida_disconnect.argtypes = []
    ida_lib.get_err.restype = ctypes.c_long
    ida_lib.get_err.argtypes = [ctypes.c_char_p, ctypes.c_int]
    ida_lib.childNodes.restype = ctypes.c_long
    ida_lib.childNodes.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.parentNode.restype = ctypes.c_long
    ida_lib.parentNode.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.setParentNode.restype = ctypes.c_long
    ida_lib.setParentNode.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.hasChildNodes.restype = ctypes.c_long
    ida_lib.hasChildNodes.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.firstChild.restype = ctypes.c_long
    ida_lib.firstChild.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.lastChild.restype = ctypes.c_long
    ida_lib.lastChild.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.nextSibling.restype = ctypes.c_long
    ida_lib.nextSibling.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.previousSibling.restype = ctypes.c_long
    ida_lib.previousSibling.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.childNodesLength.restype = ctypes.c_long
    ida_lib.childNodesLength.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.setNodeValue.restype = ctypes.c_long
    ida_lib.setNodeValue.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.cloneNode.restype = ctypes.c_long
    ida_lib.cloneNode.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.insertBefore.restype = ctypes.c_long
    ida_lib.insertBefore.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.createNode.restype = ctypes.c_long
    ida_lib.createNode.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.contains.restype = ctypes.c_long
    ida_lib.contains.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.domAncestor.restype = ctypes.c_long
    ida_lib.domAncestor.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.item.restype = ctypes.c_long
    ida_lib.item.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.appendChild.restype = ctypes.c_long
    ida_lib.appendChild.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.removeChild.restype = ctypes.c_long
    ida_lib.removeChild.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.replaceChild.restype = ctypes.c_long
    ida_lib.replaceChild.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.setAttribute.restype = ctypes.c_long
    ida_lib.setAttribute.argtypes = [ctypes.c_char_p, ctypes.c_long, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.getAttribute.restype = ctypes.c_long
    ida_lib.getAttribute.argtypes = [ctypes.c_char_p, ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.openDocument.restype = ctypes.c_long
    ida_lib.openDocument.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.openDocByTypeAndName.restype = ctypes.c_long
    ida_lib.openDocByTypeAndName.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.saveDocument.restype = ctypes.c_long
    ida_lib.saveDocument.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.runSimulation.restype = ctypes.c_long
    ida_lib.runSimulation.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.pollForQueuedResults.restype = ctypes.c_long
    ida_lib.pollForQueuedResults.argtypes = [ctypes.c_char_p, ctypes.c_int]
    ida_lib.getZones.restype = ctypes.c_long
    ida_lib.getZones.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.getWindows.restype = ctypes.c_long
    ida_lib.getWindows.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.getChildrenOfType.restype = ctypes.c_long
    ida_lib.getChildrenOfType.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.findNamedChild.restype = ctypes.c_long
    ida_lib.findNamedChild.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.exitSession.restype = ctypes.c_long
    ida_lib.exitSession.argtypes = [ctypes.c_char_p, ctypes.c_int]
    ida_lib.getAllSubobjectsOfType.restype = ctypes.c_long
    ida_lib.getAllSubobjectsOfType.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.runIDAScript.restype = ctypes.c_long
    ida_lib.runIDAScript.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.copyObject.restype = ctypes.c_long
    ida_lib.copyObject.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.findObjectsByCriterium.restype = ctypes.c_long
    ida_lib.findObjectsByCriterium.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    ida_lib.findUseOfResource.restype = ctypes.c_long
    ida_lib.findUseOfResource.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    ida_lib.printReport.restype = ctypes.c_long
    ida_lib.printReport.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_long, ctypes.c_char_p, ctypes.c_int]


def _ensure_ida_runtime_started() -> None:
    global process, pid, ida_lib
    if ida_lib is not None and process is not None and process.poll() is None:
        return

    command = path_to_ice + "ida-ice.exe \"" + path_to_ice + "ida.img\" -G 1"
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pid = str(process.pid)
    print("Process ID:", pid, "\n")

    time.sleep(5)

    if path_to_ice not in os.environ.get("PATH", ""):
        os.environ["PATH"] = path_to_ice + os.pathsep + os.environ["PATH"]

    ida_lib = ctypes.CDLL(path_to_ice + "x64\\idaapi2.dll")
    _configure_ida_lib()


# Utility functions

# def ida_poll_results_queue(time_interval):
#     size = 5000
#     doc_str = ctypes.create_string_buffer(size)
#     poll_result = False
#     while not poll_result:
#         time.sleep(time_interval)

#         ida_lib.pollForQueuedResults(doc_str, len(doc_str))
#         poll_result2 = json.loads(doc_str.value.decode("utf-8"))
#         if isinstance(poll_result2, list):
#             poll_result = poll_result2[0]['value']
#         else:
#             return ""
#     return poll_result2[1]['value']
def ida_poll_results_queue(time_interval):
    _ensure_ida_runtime_started()
    size = 5000
    doc_str = ctypes.create_string_buffer(size)
    poll_result = False

    while not poll_result:
        time.sleep(time_interval)
        ida_lib.pollForQueuedResults(doc_str, len(doc_str))

        raw = doc_str.value.decode("utf-8", errors="replace").strip()
        if not raw:
            continue

        try:
            poll_result2 = json.loads(raw)
            #print(f"Raw polled result: {raw}")
        
        except json.JSONDecodeError:
            continue

        # heartbeat dict
        if isinstance(poll_result2, dict) and poll_result2.get("type") == "bool" and poll_result2.get("value") is False:
            continue

        if isinstance(poll_result2, list) and len(poll_result2) >= 1:
            first = poll_result2[0]
            poll_result = bool(first.get("value", False)) if isinstance(first, dict) else bool(first)
        else:
            return ""

    # âœ… robust payload handling
    if isinstance(poll_result2, list) and len(poll_result2) >= 2:
        payload = poll_result2[1]
        if isinstance(payload, dict) and "value" in payload:
            return payload["value"]
        return payload

    return ""


def call_ida_api_function(fun, *args):
    """
    Just send in the function name and its unique arguments (not out buffer and out buffer length)
    """
    _ensure_ida_runtime_started()
    p = ctypes.create_string_buffer(5000)
    new_args = args + (p, len(p))
    res = fun(*new_args)
    #print(f"result from {fun.__name__}: {res}")
    if res == 0:
        return ida_poll_results_queue(0.1)
    elif res > 0:
        p = ctypes.create_string_buffer(res)
        new_args = args + (p, len(p))
        res = fun(*new_args)
        if res == 0:
            return ida_poll_results_queue(0.1)
        else:
            return ""
    else:
        res2 = ida_lib.get_err(p, len(p))
        return p.value.decode("utf-8")


def call_ida_api_function_j(fun, *args):
    """
    Just send in the function name and its unique arguments (not out buffer and out buffer length)
    """
    _ensure_ida_runtime_started()

    p = ctypes.create_string_buffer(5000)
    args = args + (p, len(p))
    res = fun(*args)
    if res == 0:
        return p
    else:
        p = ctypes.create_string_buffer(res)
        res = fun(*args)
        if res == 0:
            return p
        else:
            return ""


def ida_poll_results_queue_j(time_interval):
    _ensure_ida_runtime_started()
    size = 5000
    doc_str = ctypes.create_string_buffer(size)
    poll_result = False
    while not poll_result:
        time.sleep(time_interval)
        poll_res = ida_lib.pollForQueuedResults(doc_str, len(doc_str))
        poll_result2 = json.loads(doc_str.value.decode("utf-8"))
        if isinstance(poll_result2, list):
            poll_result = poll_result2[0]['value']
        else:
            return ""
    return json.dumps(poll_result2[1])


def ida_runSimulation(building, opt="1"):
    sim_res = call_ida_api_function(ida_lib.runSimulation, building, opt)
    return sim_res


def ida_connect(port=b"5945"):
    _ensure_ida_runtime_started()
    start = ida_lib.connect_to_ida(port, pid.encode())
    return start


def ida_disconnect():
    if ida_lib is None:
        return True
    end = ida_lib.ida_disconnect()
    return end


def ida_exit_session():
    result = call_ida_api_function(ida_lib.exitSession)
    return result


def ida_stop_process(timeout_sec: float = 5.0):
    global process, pid
    if process is None:
        return None
    try:
        if process.poll() is not None:
            return process.returncode
        process.terminate()
        process.wait(timeout=timeout_sec)
        return process.returncode
    except Exception:
        try:
            process.kill()
            process.wait(timeout=timeout_sec)
            return process.returncode
        except Exception:
            return None
    finally:
        if process is not None and process.poll() is not None:
            process = None
            pid = None


def ida_open(file_path=""):
    _ensure_ida_runtime_started()
    building = call_ida_api_function(ida_lib.openDocument, file_path.encode())

    return building


def ida_save(building, result_path="", mode=1):
    _ensure_ida_runtime_started()
    status = call_ida_api_function(ida_lib.saveDocument, building, result_path.encode(), mode)

    return status


def ida_get_named_child(par_node, child_name):
    """
    Return the child node from the parent node by passing in child_name.
    """
    site_res = call_ida_api_function(ida_lib.findNamedChild, par_node, child_name.encode())
    return site_res


def ida_get_named_parent(child_node, par_name):
    """
    Return the parent node from the child node by passing in par_name.
    """
    site_res = call_ida_api_function(ida_lib.child_node, child_node, par_name.encode())
    return site_res


def ida_get_name(node):
    """
    Return the name of the node.
    """
    val = call_ida_api_function(ida_lib.getAttribute, b"NAME", node)
    return val


def ida_get_value(node):
    """
    Return the value of the node
    """
    val = call_ida_api_function(ida_lib.getAttribute, b"VALUE", node)
    return val


def ida_set_value(node, text):
    """
    Set value to the node by passing in text
    Return: True/False
    """
    val = call_ida_api_function(ida_lib.setAttribute, b"VALUE", node, text.encode())
    return val


def ida_get_childrenTypedList(par_node, child_name):
    """
    Get the children nodes with types from parent node  by passing in child_name
    Returned Example: [{'type': 'object', 'value': 2}, {'type': 'object', 'value': 3}]
    """
    val = call_ida_api_function(ida_lib.getChildrenOfType, par_node, child_name)
    return val


def showChildrenList(par_node):
    """
    Return children names of parent node as list ["chile_name1","chile_name2","chile_name3"].
    """
    children_nodes_jsonList = call_ida_api_function(ida_lib.childNodes, par_node)
    nameList = []
    for child_node in children_nodes_jsonList:
        name = ida_get_name(child_node['value'])
        nameList.append(name)

    str(nameList)
    return nameList


def showChildrenDict(par_node):
    """
    Return children {nodes, names} from the parent node
    """
    children_nodes_jsonList = call_ida_api_function(ida_lib.childNodes, par_node)
    nameDict = {}
    for child_node in children_nodes_jsonList:
        name = ida_get_name(child_node['value'])
        nameDict[child_node['value']] = name

    str(nameDict)
    return nameDict


def ida_get_zonesList(node):
    """
    Return a list of all zones from e.g., building node
    """
    windows = call_ida_api_function(ida_lib.getZones, node)
    return windows


def ida_get_windowsList(node):
    """
    Return a list of all windows from e.g., building or zone node
    """
    windows = call_ida_api_function(ida_lib.getWindows, node)
    return windows




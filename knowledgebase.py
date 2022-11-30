import config
import datetime
import ipaddress
import json
import pathlib
import pickle
import platform
import requests

BAYSE_KB_CACHE_DIRNAME = "bayse_kb"
CACHE_EXPIRATION_AS_FLOAT_SECONDS = 86400.00  # one day


def get_destination_info(session, dst, protocolinfo, port, use_cache=True, verbose=False):
    """Either queries the Destination Knowledgebase or loads data from the cache. Returns the resulting data.
    """
    data = None
    if port:
        url = f"{config.BAYSE_KB_API_URL}?name={dst}&protocol={protocolinfo}&port={port}&getStatistics=true" \
              f"&getFlowSummary=true"
    else:
        url = f"{config.BAYSE_KB_API_URL}?name={dst}&protocol={protocolinfo}&getStatistics=true&getFlowSummary=true"
    # determine if cached results exist and are still valid
    if use_cache:
        if verbose:
            print("we want to use the cache...do we have data?")
        # try to retrieve
        data = retrieve_cached_results(dst, session, url)
        if data:
            if verbose:
                print("Got data from cache")
        else:
            # if nothing stored, save and return that data
            print("Nothing stored, so getting a fresh copy to save")
            response = session.get(url)
            data = get_kb_data_from_response(response)
            data = save_results_to_cache(dst, data)
    else:
        response = session.get(url)
        data = get_kb_data_from_response(response)
    return data


def get_kb_data_from_response(response):
    """Since we need to work through the response data in a few scenarios, this function handles taking a raw
       response and returning only the JSON data we want (or None if no/invalid data).
    """
    kb_data = None
    if response.status_code == 200:
        try:
            if "body" in response.json():
                return response.json()["body"]
        except:
            return kb_data
    return kb_data


def get_filename(destination):
    """Gets (and creates, if it doesn't exist) the cache directory where pickle data is stored and creates the filename.
    """
    if platform.system().lower() == "windows":
        destination_kb_cache_dir = str(pathlib.PurePath(f"C:\\TEMP\\{BAYSE_KB_CACHE_DIRNAME}"))
        delimiter = "\\"
    else:
        destination_kb_cache_dir = str(pathlib.PurePath(f"/tmp/{BAYSE_KB_CACHE_DIRNAME}"))
        delimiter = "/"
    pathlib.Path(destination_kb_cache_dir).mkdir(parents=True, exist_ok=True)  # make sure it exists
    filename = f"{destination_kb_cache_dir}{delimiter}{destination}.pkl"
    return filename


def save_results_to_cache(destination, kb_data):
    """This occurs when we don't have cached Destination KB results and want to save some. Generally, we should cache
       when we don't AND when the results look fully-formed.
    """
    now_utc = float(datetime.datetime.utcnow().strftime('%s'))
    filename = get_filename(destination)
    try:
        cache_file = open(filename, "wb")
        # add a last_saved field that identifies the current time
        kb_data["last_saved"] = now_utc
        pickle.dump(kb_data, cache_file)
        #print("Successfully saved Destination KB Data to cache.")
        cache_file.close()
    except Exception as e:
        print(f"Failed to save Destination KB Data to temporary cache: {e}")
        try:
            cache_file.close()
        except:
            pass


def retrieve_cached_results(destination, session, url):
    """Retrieves Destination Knowledgebase results that are cached and returns them to object format. If the results
       indicate that the last observed time is more than two weeks ago, a new lookup should occur, be saved (if it's
       fully-formed), and then returned in place of the existing cache result.
    """
    get_fresh = False
    kb_data = None
    filename = get_filename(destination)
    try:
        cache_file = open(filename, "rb")
        kb_data = pickle.load(cache_file)
    except pickle.UnpicklingError as e:
        print(f"Error unpickling: {e}")
        get_fresh = True
        cache_file.close()
    except:
        get_fresh = True
        try:
            cache_file.close()
        except:
            pass
    """Check to see if the cached Destination KB result was last saved more than 1 day ago. If so, request a fresh 
       Desination KB lookup and store it (if it looks okay).
    """
    now_utc = float(datetime.datetime.utcnow().strftime('%s'))
    try:
        if kb_data and "last_saved" in kb_data:
            last_saved_time = kb_data["last_saved"]
            if now_utc - CACHE_EXPIRATION_AS_FLOAT_SECONDS >= last_saved_time:  # should request a fresh copy
                get_fresh = True
        else:
            get_fresh = True
    except:
        get_fresh = True
    if get_fresh:
        response = session.get(url)
        kb_data = get_kb_data_from_response(response)
        if kb_data:
            save_results_to_cache(destination, kb_data)
        else:
            print("New results don't look right. Not saving.")
    # remove the cache file's last_saved field, if it exists
    try:
        del kb_data["last_saved"]
    except:
        pass
    return kb_data


def add_knowledge_for_files_in_dir(directory):
    """Takes a directory containing BayseFlow files. For each file, infuses it with destination_knowledge and
    parent_knowledge, destination_stats, and destination_flow_summary information from Bayse.
    """
    print(f"Adding Bayse Knowledge for files in {directory}")
    s = requests.Session()
    use_cache = True  # uses the cache temporarily within the same run to avoid hitting the database unnecessarily
    cached_dests = set()
    for fname in pathlib.Path(directory).iterdir():
        infused_filename = f"{directory}/{fname.name}"
        infused_data = dict()
        if fname.is_file() and fname.name.endswith(".bf"):
            data = None
            with open(fname, 'r', encoding='utf-8') as f:
                data = json.loads(f.read())
            if data:
                start_ts = float(data["trafficDate"])
                infused_data = {"hash": data["hash"],
                                "trafficDate": data["trafficDate"],
                                "fileName": data["fileName"],
                                "BayseFlows": []
                                }
            for flow in data["BayseFlows"]:
                query_bayse_knowledge = True
                if flow["protocolInformation"] == "ICMP":
                    dst = flow["dst"]
                    port = None
                else:
                    dst_data = flow["dst"].split(":")
                    port = int(dst_data[-1])
                    dst = ":".join(dst_data[0:-1])  # handles ipv6 safely
                if flow["destinationNameSource"] == "original":
                    try:
                        if ipaddress.ip_address(dst).is_private:
                            flow["destination_knowledge"] = {}
                            flow["destination_stats"] = {}
                            flow["destination_flow_summary"] = {}
                            flow["parent_knowledge"] = {}
                            query_bayse_knowledge = False
                    except Exception as e:
                        print(f"Got an unexpected exception with {dst}: {e}")
                if query_bayse_knowledge:
                    kb_data = get_destination_info(s, dst, flow["protocolInformation"], port, use_cache)
                    if use_cache:
                        cached_dests.add(dst)  # track all of the destinations we need to delete caches for afterwards
                    try:
                        save_data = kb_data["destination_info"]["knowledge"]
                        try:
                            nameport = list(save_data.keys())[0]
                            info = save_data[nameport]
                        except:
                            nameport = None
                            info = {}
                        flow["destination_knowledge"] = {"destination_nameport": nameport, "info": info}
                    except:
                        flow["destination_knowledge"] = None
                    try:
                        save_data = kb_data["destination_info"]["statistics"]
                        flow["destination_stats"] = save_data
                    except:
                        flow["destination_stats"] = None
                    try:
                        save_data = kb_data["destination_info"]["flow_summary"]
                        try:
                            nameport = list(save_data.keys())[0]
                            info = save_data[nameport]
                        except:
                            nameport = None
                            info = {}
                        flow["destination_flow_summary"] = {"destination_nameport": nameport, "info": info}
                    except:
                        flow["destination_flow_summary"] = None
                    try:
                        save_data = kb_data["parent_info"]["knowledge"]
                        try:
                            nameport = list(save_data.keys())[0]
                            info = save_data[nameport]
                        except:
                            nameport = None
                            info = {}
                        flow["parent_knowledge"] = {"parent_nameport": nameport, "info": info}
                    except:
                        flow["parent_knowledge"] = None
                    infused_bayseflow = {
                        "src": flow["src"],
                        "dst": flow["dst"],
                        "destinationNameSource": flow["destinationNameSource"],
                        "srcPkts": flow["srcPkts"],
                        "srcBytes": flow["srcBytes"],
                        "dstPkts": flow["dstPkts"],
                        "dstBytes": flow["dstBytes"],
                        "relativeStart": flow["relativeStart"],
                        "protocolInformation": flow["protocolInformation"],
                        "identifier": flow["identifier"],
                        "duration": flow["duration"],
                        "label": flow["label"],
                        "destination_knowledge": flow["destination_knowledge"],
                        "destination_stats": flow["destination_stats"],
                        "destination_flow_summary": flow["destination_flow_summary"],
                        "parent_knowledge": flow["parent_knowledge"]
                    }
                    infused_data["BayseFlows"] += [infused_bayseflow]
        with open(infused_filename, "w") as infused_outfile:
            json.dump(infused_data, infused_outfile)
    if cached_dests:
        #print(f"Cleaning up {len(cached_dests)} cache entries to avoid state issues.")
        for d in cached_dests:
            fname = get_filename(d)
            pathlib.Path(fname).unlink(missing_ok=True)
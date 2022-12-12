import argparse
import bayse_summary
import config
import interpret
import knowledgebase as kb
import sys
import time
from pathlib import Path
from bayse_tools.converter import convert



def convert_and_label_files(connlogs, dnslogs, pcaps, outdir, timing=False, noupload=False):
    """Takes a set of zero or more conn.log files and dns.log files, converts them into their BayseFlow format,
       and labels them. The labeling functionality will also upload their stats to the cloud.
    """
    share = not noupload
    combinedlogs = None
    if dnslogs:
        combinedlogs = dict(zip(connlogs, dnslogs))
    if combinedlogs:
        for log in combinedlogs:
            if timing:
                start_time = time.perf_counter()
            else:
                start_time = None
            print(f"Converting {log}")
            convert.convert_zeek(log, zeek_dnsfile_location=combinedlogs[log], output_dir=outdir, should_label=True,
                                 api_key=config.API_KEY, labeling_path=config.LABELING_BINARY_DIR,
                                 converter_start=start_time, share_stats=share)
    else:
        for log in connlogs:
            if timing:
                start_time = time.perf_counter()
            else:
                start_time = None
            convert.convert_zeek(log, output_dir=outdir, should_label=True, api_key=config.API_KEY,
                                 labeling_path=config.LABELING_BINARY_DIR, converter_start=start_time,
                                 share_stats=share)
    if pcaps:
        for pcap in pcaps:
            print(f"Converting {pcap}")
            if timing:
                start_time = time.perf_counter()
            else:
                start_time = None
            convert.convert_pcap(pcap, output_dir=outdir, should_label=True, api_key=config.API_KEY,
                                 labeling_path=config.LABELING_BINARY_DIR, converter_start=start_time,
                                 share_stats=share)




def process_all_inputs(current_directory, output_directory, timing, noupload=False):
    """Recursively converts, labels, uploads (optionally), and pulls in information from the Bayse knowledgebase for
       all valid files at the current directory level."""
    pcaps, connlogs, dnslogs, subdirs = collect_all_valid_at_level(current_directory)
    print(f"About to process {len(pcaps)} PCAPs and {len(connlogs)} Zeek logs found in {current_directory}")
    convert_and_label_files(connlogs, dnslogs, pcaps, output_directory, timing, noupload)
    kb.add_knowledge_for_files_in_dir(output_directory)


def collect_all_valid_at_level(directory):
    """Takes a directory and collects all valid input files to be processed at that level. Any subdirectories (that
       will be processed in a later call of this function) are also captured here."""

    subdirs_to_process = []
    zeek_files = dict()
    pcap_files = []
    connlogs = set()
    dnslogs = set()
    for f in Path(directory).iterdir():
        if f.is_file():
            if f.name.endswith("conn.log"):
                if f.stem not in zeek_files:
                    zeek_files[f.stem] = {"conn": None, "dns": None}
                zeek_files[f.stem]["conn"] = f.absolute()
            elif f.name.endswith("dns.log"):
                if f.stem not in zeek_files:
                    zeek_files[f.stem] = {"conn": None, "dns": None}
                zeek_files[f.stem]["dns"] = f.absolute()
            elif f.suffix.upper() in [".CAP", ".PCAP", ".PCAPNG"]:
                pcap_files += [f.absolute()]
        elif Path.is_dir(f):
            subdirs_to_process += [f]
    for zeek in zeek_files:
        if zeek_files[zeek]["dns"]:
            dnslogs.add(zeek_files[zeek]["dns"])
        if zeek_files[zeek]["conn"]:
            connlogs.add(zeek_files[zeek]["conn"])
    return pcap_files, connlogs, dnslogs, subdirs_to_process


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--e2e", help=f"given a directory, perform entire e2e process. Recurses through subdirectories."
                        , type=str, default=None)
    parser.add_argument("--outputdirectory", help="directory where BayseFlow files should be stored", type=str,
                        default="/tmp/bayseflows")
    parser.add_argument("-t", "--timing", help="capture diagnostics about timing of each step", action="store_true")
    parser.add_argument("--noupload", help="add this to avoid processing statistics in the cloud", action="store_true")
    parser.add_argument("--interpret", help=f"a URL or destination that should be interpreted", type=str, default=None)
    parser.add_argument("-s", "--screenshot", help=f"Should we capture a screenshot of the URL?",
                        action='store_true', default=False)
    parser.add_argument("-d", "--details", help=f"Should we capture the destination details that were found when "
                                                f"visiting a URL?", action='store_true', default=False)
    parser.add_argument("--url", help=f"The URL where an interpret result is stored."
                        , type=str, default=None)
    args = parser.parse_args()

    if args.e2e:
        if Path(args.e2e).is_dir():
            process_all_inputs(args.e2e, args.outputdirectory, args.timing, args.noupload)
        else:
            print(f"{args.e2e} is not a directory. Please supply a directory for this argument!")
        sys.exit()
    else:
        if not args.url:
            if not args.interpret:
                parser.print_help()
                sys.exit(1)
            print(f"Sending {args.interpret} to be interpreted")
            result = interpret.interpret_url(args.interpret, args.screenshot, args.details)
            interpret.get_interpret_result(result)
        else:
            print(f"Ignoring all other args and interpreting passed in URL.")
            interpret.get_interpret_result(args.url)


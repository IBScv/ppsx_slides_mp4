#!/usr/bin/env python3

#############################################################
#                                                           #
#       PPSX to MP4 converter                               #
#       @author: Edson Martins <propiebis@gmail.com>       #
#                                                           #
#############################################################

"""
ppsx2mp4.py

Convert PPSX with:
    slide image + narration m4a

into MP4.

Usage:

python3 ppsx2mp4.py input.ppsx output.mp4

"""

import zipfile
import tempfile
import shutil
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET


REL_NS = {
    "r":
    "http://schemas.openxmlformats.org/package/2006/relationships"
}

#extract ppsx file (its like a zip file)
def extract_ppsx(filename):

    temp = Path(tempfile.mkdtemp())

    with zipfile.ZipFile(filename) as z:
        z.extractall(temp)

    return temp


#read and extract info from slides
def get_slide_files(root):

    slides = root / "ppt/slides"

    return sorted(
        slides.glob("slide*.xml"),
        key=lambda x:
        int(x.stem.replace("slide",""))
    )


#get all Relationship nodes to find out the medias associated
def get_relationships(root, slide):

    rel_file = (
        root /
        "ppt/slides/_rels" /
        (slide.name + ".rels")
    )

    result = {}

    if not rel_file.exists():
        return result


    tree = ET.parse(rel_file)

    for r in tree.findall(
        "r:Relationship",
        REL_NS
    ):

        rid = r.attrib["Id"]

        target = r.attrib["Target"]

        result[rid] = target


    return result



#find the meadias associated to the slides now doing only one image and first audio track
def find_media(root, slide):

    rel_file = (
        root /
        "ppt/slides/_rels" /
        (slide.name + ".rels")
    )

    image = None
    audio = None


    tree = ET.parse(rel_file)


    for rel in tree.findall(
        "r:Relationship",
        REL_NS
    ):

        target = rel.attrib["Target"]
        rtype = rel.attrib["Type"]


        # first image only
        if image is None:
            if (
                "image" in rtype
                and target.lower().endswith(
                    (
                        ".png",
                        ".jpg",
                        ".jpeg"
                    )
                )
            ):
                image = target


        # first audio only
        if audio is None:
            if (
                "audio" in rtype
                and target.endswith(".m4a")
            ):
                audio = target


        # stop when both found
        if image and audio:
            break


    return image, audio


import subprocess
import re

def get_duration(audio):

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio)
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True
    )

    try:
        return float(result.stdout.strip())

    except ValueError:
        print("Cannot read duration:", audio)
        print("ffprobe output:", result.stdout)
        return 0


def create_slide_video(image, audio, output, slide_num, total):

    cmd = [
        "ffmpeg",

        "-hide_banner",
        "-loglevel",
        "error",

        "-y",

        "-loop",
        "1",

        "-i",
        str(image),
    ]


    if audio:
        cmd += [
            "-i",
            str(audio),
            "-shortest",
        ]

    else:
        # silent slide duration
        cmd += [
            "-t",
            "10",
        ]


    cmd += [

        "-vf",
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2",

        "-c:v",
        "libx264",

        "-pix_fmt",
        "yuv420p",

        "-progress",
        "pipe:1",

        "-nostats",

        str(output)
    ]


    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1
    )


    duration = get_duration(audio) if audio else 10 #default 10 seconds for slide without audio

    current = 0


    for line in iter(process.stdout.readline, ''):

        line = line.strip()

        if line.startswith("out_time_ms="):

            value = line.split("=", 1)[1]

            if value.isdigit():

                current = int(value) / 1000000

                percent = min(
                    (current / duration) * 100,
                    100
                )

                #print(
                 #   f"\rSlide {slide_num}/{total} "
                 #   f"{percent:6.2f}%",
                 #   end="",
                 #   flush=True
                #)
                show_progress(
                    slide_num,
                    total,
                    percent
                )


        elif line == "progress=end":

            print(
                f"\rSlide {slide_num}/{total} 100.00%"
            )


    process.wait()

    print()

def concatenate(files, output):

    txt = Path("concat.txt")


    with txt.open("w") as f:

        for x in files:
            f.write(
                f"file '{x}'\n"
            )


    subprocess.run([

        "ffmpeg",

        "-hide_banner",
        "-loglevel",
        "error",
        "-y",

        "-f",
        "concat",

        "-safe",
        "0",

        "-i",
        str(txt),

        "-c",
        "copy",

        str(output)

    ],check=True)



def main():

    if len(sys.argv)<3:

        print(
            "Usage: python3 ppsx2mp4.py input.ppsx output.mp4"
        )
        return


    ppsx = sys.argv[1]

    output = sys.argv[2]


    root = extract_ppsx(ppsx)


    slides = get_slide_files(root)


    videos=[]


    work = Path("rendered")

    work.mkdir(
        exist_ok=True
    )


    for index,slide in enumerate(slides,1):

        img,audio=find_media(
            root,
            slide
        )


        if not img and not audio:

            print(
                "Skipping",
                slide
            )
            continue


        #print("DEBUG: Slide ", index, slide.name, "IMAGE=", img, "AUDIO=", audio)
        
        #sanitize the paths
        image_path = (
            root /
            "ppt" /
            img.replace("../","")
        )

        if not audio:
            audio_path = None
        else:
            audio_path = (
                root /
                "ppt" /
                audio.replace("../","")
            )



        #print(
        #    "Slide",
        #    index,
        #    image_path.name,
        #    audio_path.name
        #)


        out = (
            work /
            f"slide{index}.mp4"
        )


        create_slide_video(
            image_path,
            audio_path,
            out,
            index,
            len(slides)
        )


        videos.append(out)



    concatenate(
        videos,
        output
    )


    shutil.rmtree(
        root
    )


    print(
        "DONE:",
        output
    )


#show a progressbar for each conversion
def show_progress(slide_num, total, percent):

    width = 30

    filled = int(width * percent / 100)

    bar = "█" * filled + "-" * (width-filled)

    print(
        f"\rSlide {slide_num}/{total} \t\t"
        f" [{bar}] {percent:6.2f}%",
        end="",
        flush=True
    )

if __name__=="__main__":
    main()
# Re-creating the Internet topology from RIS / Routeviews 

## Goal

I want to be able to recreate the Internet topology from processing MRT files produced by RIPE RIS.

The output I expect is a text file with the following information: 

  - One line per link 
  - Each line has "<as number 1> <as number 2>" meaning that that there is a line between AS1 and AS2

We will identify the links by processing the AS PATHS contained in the MRT files. An AS Path "AS1 AS2 AS3 AS4" means that links exist between AS1 and AS2, between AS2 and AS3 and between AS3 and AS4.

We don't want duplicate links in the output. 

## Where to find RIS Data

The MRT files live in canonical URLs with the format: https://data.ris.ripe.net/rrcXX/YYYY.MM/TYPE.YYYYMMDD.HHmm.gz

RIS collects routing data from _collectors_, identified by rrc00, rrc01...rrc25.

## Tech Stack

For our scripts we will use python3, instrumented through uv. Our uv project has already been initalized. We will use dependencies as needed, including: 

   - typer for cli options and colorful output

For processing the MRT files and converting them to text we have bgpreader installed in the system. See the file bgpreader.txt for the command linke switches available in MRT.

## Pipeline 

MRT files are binary and contain a lot of information. I want to structure this project along the lines of a pipeline.

### Step 1 : download MRT binary files

A script called get-mrt.py that receives the following flags: 
   - --collectors : a comma separated list of rrc collectors to get mrt files from 
   - --date : a date in YYYYMMDD format that specify which mrt files to get
   - --output-dir : a directory where the downloaded files will be stored. Defaults to ./mrt

The script will download the MRT binary files and store them in the output directory.

Additional considerations: 
   - If a MRT file already exists locally it should not be downloaded again
   - When downloading multiple files, provide visual feedback of files downloaded, files remaining
   - Always measure execution time and display it when exiting
   - This and all scripts are to be properly documented inline and have rich --help output

### Step 2 : extract AS PATHS from the MRT binary files

A Script called process-mrt.py that receives the following command line flags:
   - --input-files : receives a glob of binary mrt files to process
   - --output-dir : output directory for extracted as paths, defaults to ./paths

This is script will open, calling bgpreader, the binary files, extract the AS PATHS from the MRT files and write them onto text files that have the same name as the input file but end in .txt

Additional considerations: 
   - When processing multiple files, provide visual feedback of files processed, files remaining
   - Always measure execution time and display it when exiting
   - If a txt file corresponding to an input MRT file already exists, the MRT file is not to be processed again

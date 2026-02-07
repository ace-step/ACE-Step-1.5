Date of the program this worked:
07.02.2026 - 10:40 am UTC +1

ACE-Step1.5 Rocm Manual for cachy-os and tested with RDNA4/Strix Halo.
Strix-Halo need manually set to be 16GB VRAM in Bios or more.
At this moment no GTT Ram size used.

#Install python Version 3.11
sudo pacman -S python311 git 

#Navigate to the folder you want ACE-Step to be in and open the terminal there

# Get the Program and change into the folder
git clone https://github.com/ace-step/ACE-Step-1.5.git
cd ACE-Step-1.5/ 

#Create the virtual python enviroment with python Version 3.11
python3.11 -m venv .venv

#activate the enviroment in the terminal
source .venv/bin/activate

#install pytorch requirements
pip install torch torchaudio torchvision xformers --index-url https://download.pytorch.org/whl/rocm6.4

#install requirements without uv
pip install -r requirements-rocm-linux.txt

#start the program 
#"--servername 0.0.0.0" is for making this on all networks card available
#"--servername 127.0.0.1" is for making this just local available
#"--servername localhost" or no without the "--servername" option also local only
python -m acestep.acestep_v15_pipeline --server-name 0.0.0.0 --port 7680

#start the program local
python -m acestep.acestep_v15_pipeline --server-name 127.0.0.1 --port 7680

# Access the webui on your Browser
http://127.0.0.1:7680

#deactivate int8
#set 5Hz LM Backend to "pt"
#Click initialize and wait for download to finish
#Have fun


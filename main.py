#! /usr/bin/python3

# Import Standard Libraries
import fcntl
import multiprocessing
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser


# Import Third Party Libraries
from gi.repository import Gtk, Gdk, GObject, GLib
#import dialogs

# Setting base app information, such as version, and configuration directories/files.
progVer = "0.3"
confDir = "/etc/netctl"
statusDir = "/usr/lib/netgui/"
intFile = statusDir + "interface.cfg"
iwconfigFile = statusDir + "iwlist.log"
iwlistFile = statusDir + "iwlist.log"
pidFile = statusDir + "program.pid"
imgLoc = "/usr/share/netgui/imgs"
pidNumber = os.getpid()
prefFile = statusDir + "preferences.cfg"

# Allows for command line arguments. Currently only a "Help" argument, but more to come.
# TODO import ext libary to handel this for us
for arg in sys.argv:
    if arg == '--help' or arg == '-h':
        print("netgui; The NetCTL GUI! \nWe need root :)")
        sys.exit(0)
    if arg == '--version' or arg == '-v':
        print("Your netgui version is " + progVer + ".")
        sys.exit(0)    

if os.path.exists(statusDir):
    pass
else:
    subprocess.call("mkdir " + statusDir, shell=True)
                      
# Let's make sure we're root, while at it.
euid = os.geteuid()
if euid != 0:
    print("netgui NEEDS to be run as root, since many commands we use requires it.\nPlease sudo or su -c and try again.")
    sys.exit(77)

# Let's also not allow any more than one instance of netgui.
fp = open(pidFile, 'w')
try:
    fcntl.lockf(fp, fcntl.LOCK_EX|fcntl.LOCK_NB)
except IOError:
    print("We only allow one instance of netgui to be running at a time for precautionary reasons.")
    sys.exit(1)

fp.write(str(pidNumber)+"\n")
fp.flush()

# The main class of netgui. Nifty name, eh?
class netgui(Gtk.Window):
    # AFAIK, I need __init__ to call InitUI right off the bat. I may be wrong, but it works.
    def __init__(self):
        self.InitUI()
        
        
    # Since I LOVE everything to be organized, I use a separate InitUI function so it's clean.
    def InitUI(self):
        IsConnected()
        # Create a "Builder", which basically allows me to import the Glade file for a complete interface.
        # I love Glade, btw. So much quicker than manually coding everything.
        self.builder = Gtk.Builder()
        self.builder.add_from_file("UI.glade")
        
        # Init Vars
        self.scanning = False
        self.APindex = 0  
        self.p = None
        #self.interfaceName = None
        
        # Grab the "window1" attribute from UI.glade, and set it to show everything.
        window = self.builder.get_object("mainWindow")
        window.connect("delete-event", Gtk.main_quit)
        
        
        # Setup the main area of netgui: The network list.
        self.APList = self.builder.get_object("treeview1")
        self.APStore = Gtk.ListStore(str, str, str, str)
        self.APList.set_model(self.APStore)
        
        # Set Up Columns
        # renderer1 = The Cell renderer. Basically allows for text to show.
        # column1 = The actual setup of the column. Arguments = title, CellRenderer, textIndex)
        # Actually append the column to the treeview.
        SSIDCellRenderer = Gtk.CellRendererText()
        SSIDColumn = Gtk.TreeViewColumn("SSID", SSIDCellRenderer, text=0)
        self.APList.append_column(SSIDColumn)
        
        connectQualityCellRenderer = Gtk.CellRendererText()
        connectQualityColumn = Gtk.TreeViewColumn("Connection Quality", connectQualityCellRenderer, text=1)
        self.APList.append_column(connectQualityColumn)
        
        securityTypeCellRenderer = Gtk.CellRendererText()
        securityTypeColumn = Gtk.TreeViewColumn("Security Type", securityTypeCellRenderer, text=2)
        self.APList.append_column(securityTypeColumn)
        
        connectedCellRenderer = Gtk.CellRendererText()
        connectedColumn = Gtk.TreeViewColumn("Connected?", connectedCellRenderer, text=3)
        self.APList.append_column(connectedColumn)
        
        # Set TreeView as Reorderable
        self.APList.set_reorderable(True)
        
        # Setting the selection detection. Heh, that rhymes.        
        
        # Set all the handlers I defined in glade to local functions.
        handlers = {
        "onExit": self.onExit,
        "onAboutClicked": self.aboutClicked,
        "onScan": self.startScan,
        "onConnect": self.connectClicked,
        "onDConnect": self.dConnectClicked,
        "onPrefClicked": self.prefClicked,
        "onHelpClicked": self.helpClicked,
        "onIssueReport": self.reportIssue
        }
        # Connect all the above handlers to actually call the functions.
        self.builder.connect_signals(handlers)
        
        # This should automatically detect their wireless device name. I'm not 100% sure
        # if it works on every computer, but we can only know from multiple tests. If 
        # it doesn't work, I will re-implement the old way.
        if os.path.isfile(intFile) != True:
            intNameCheck = str(subprocess.check_output("cat /proc/net/wireless", shell=True))
            self.interfaceName = intNameCheck[166:172]
            f = open(intFile, 'w')
            f.write(self.interfaceName)
            f.close()
        else:
            f = open(intFile, 'r')
            self.interfaceName = f.readline()
            f.close()
            
        # Start initial scan
        self.startScan(None)
        window.show_all()
                    
    def onExit(self, e):
        if self.p == None:
            pass
        else:
            self.p.terminate()
        #cleanup()
        sys.exit()
        Gtk.main_quit()
        
    # This class is only here to actually start running all the code in "onScan" in a separate process.
    def startScan(self, e):
        self.p = multiprocessing.Process(target=self.onScan)
        self.p.start()
        self.p.join()
        self.checkScan()

    def onScan(self, e=None):
        print("please wait, now scanning!")
        # Open file that we will save the command output to, run the CheckOutput function on that
        # command, which in turn will turn it from bytes into a unicode string, and close the file.
        iwf = open(iwlistFile, 'w')
        command = "iwlist " + self.interfaceName + " scan"
        output = CheckOutput(self, command)
        iwf.write(output)
        iwf.close()
        print("I finished scanning!")
        
    def checkScan(self):
        self.APStore.clear()
        
        # Run 3 separate grep commands to find various items we will need.
        grepCmd = "grep 'ESSID' " + iwlistFile
        grepCmd2 = "grep 'Encryption key:\|WPA' " + iwlistFile
        grepCmd3 = "grep 'Quality' " + iwlistFile
        print("I ran the grep commands!")
        
        # Check the output of the grep commands, and clean them up for presentation.
        output = CheckGrep(self, grepCmd).replace('ESSID:', '').replace('"', '').replace(" ", '').split("\n")
        output2 = CheckGrep(self, grepCmd2).replace(' ', '').replace('Encryptionkey:', '').replace("\nIE", '').replace(":WPAVersion", '').split("\n")
        output3 = CheckGrep(self, grepCmd3).replace(' ', '').split("\n")
        
        # Fix the quality signals to show only the quality (i.e., 68/70) instead of everything else
        # i.e., Quality = 68/70 Signal Level=-52dBm
        for i in range(len(output3)):
            strings = output3[i]
            strings = strings[8:13]
            output3[i] = strings
        print("I cleaned up the grep commands!")
            
        # Create a dictionary so we can set separate treeiters we can access to make this work.
        aps = {}
        print("I created a dictionary!")
        
        # set an int that we will convert to str soon.
        i = 0
        # For each network located in the original grep command, add it to a row, while creating that same
        # row.
        for network in output:
            aps["row" + str(i)] = self.APStore.append([network, "", "", ""])
            i = i + 1
            print("I added " + network)

        # Set i back to zero. For each item in the second grep command, convert the name to
        # a human-meaningful one, and add it to the relevant network.
        i = 0
        for encrypt in output2:
            if encrypt == "on1":
                encryption = "WPA"
            elif encrypt == "on2":
                encryption = "WPA2"
            elif encrypt == "off":
                encryption = "Open"
            else:
                encryption = "WEP"
            self.APStore.set(aps["row" + str(i)], 1, encryption)
            i = i + 1
            print("I added " + encryption)

        # Set i back to zero. For each detected quality, add it to the relevant network.
        i = 0
        for quality in output3:
            self.APStore.set(aps["row" + str(i)], 2, quality)
            i = i + 1
            print("I added " + quality)

        # Set i back to zero. Check if we are connected to a network. If we ARE, find out
        # which one we are connected to.
        i = 0
        if IsConnected() == False:
            for network in output:
                self.APStore.set(aps["row" + str(i)], 3, "No")
                i = i + 1
        else:
            i = 0
            connectedNetwork = CheckOutput(self, "netctl list | sed -n 's/^\* //p'").strip()
            for network in output:               
                if network == connectedNetwork:
                    self.APStore.set(aps["row" + str(i)], 3, "Yes")
                    i = i + 1
                else:                
                    self.APStore.set(aps["row" + str(i)], 3, "No")
                    i = i + 1
                    
        print("OnScan is finished!")
        
    def responseToDialog(entry, dialog, response):
        dialog.response(response)
            
    def getText(self):
        #base this on a message dialog
        dialog = Gtk.MessageDialog(
            None,
            Gtk.DIALOG_MODAL | Gtk.DIALOG_DESTROY_WITH_PARENT,
            Gtk.MESSAGE_QUESTION,
            Gtk.BUTTONS_OK,
            None)
        dialog.set_markup('Please enter the password for your network:')
        #create the text input field
        entry = Gtk.Entry()
        #allow the user to press enter to do ok
        entry.connect("activate", responseToDialog, dialog, Gtk.RESPONSE_OK)
        #create a horizontal box to pack the entry and a label
        hbox = Gtk.HBox()
        hbox.pack_start(Gtk.Label("Name:"), False, 5, 5)
        hbox.pack_end(entry)
        #add it and show it
        dialog.vbox.pack_end(hbox, True, True, 0)
        dialog.show_all()
        #go go go
        dialog.run()
        text = entry.get_text()
        dialog.destroy()
        return text    
    
    def connectClicked(self, menuItem):
        select = self.APList.get_selection()
        networkSSID = self.getSSID(select)
        networkSecurity = self.getSecurity(select)
        password = self.getText()
        #CreateConfig(networkSSID, self.interfaceName, networkSecurity, "")
    
    def getSSID(self, selection):
        model, treeiter = selection.get_selected()
        if treeiter != None:
            return model[treeiter][0]
        
    def getSecurity(self, selection):
        model, treeiter = selection.get_selected()
        if treeiter != None:
            securityType =  model[treeiter][2] 
            securityType = securityType.lower()
            return securityType
        
    def dConnectClicked(self, menuItem):
        pass
    
    def prefClicked(self, menuItem):
        # Setting up the cancel function here fixes a wierd bug where, if outside of the prefClicked function
        # it causes an extra button click for each time the dialog is hidden. The reason we hide the dialog
        # and not destroy it, is it causes another bug where the dialog becomes a small little
        # titlebar box. I don't know how to fix either besides this.
        def cancelClicked(self):
            print("Cancel Clicked.")
            preferencesDialog.hide()  
            
        # Setting up the saveClicked function within the prefClicked function just because it looks cleaner
        # and because it makes the program flow more, IMHO
        def saveClicked(self):
            print("Saving... eventually.")        
            
        # Get the three things we need from UI.glade
        preferencesDialog = self.builder.get_object("prefDialog")
        saveButton = self.builder.get_object("saveButton")
        cancelButton = self.builder.get_object("cancelButton")
        
        # Connecting the "clicked" signals of each button to the relevant function.
        saveButton.connect("clicked", saveClicked)
        cancelButton.connect("clicked", cancelClicked)
        
        # Opening the Preferences Dialog.
        preferencesDialog.run()
    
    def helpClicked(self, menuItem):
        # For some reason, anything besides subprocess.Popen
        # causes an error on exiting out of yelp...
        subprocess.Popen("yelp")
    
    def reportIssue(self, menuItem):
        # Why would I need a local way of reporting issues when I can use github? Exactly. 
        # And since no more dependencies are caused by this, I have no problems with it.
        webbrowser.open("https://github.com/codywd/WiFiz/issues")
    
    def aboutClicked(self, menuItem):
        # Getting the about dialog from UI.glade
        aboutDialog = self.builder.get_object("aboutDialog")
        # Opening the about dialog.
        aboutDialog.run()
        # Hiding the about dialog. Read in "prefDialog" for why we hide, not destroy.
        aboutDialog.hide() 
        
class NetCTL(object):
    # These functions are to separate the Netctl code
    # from the GUI code.
    def __init__(self):
        super(NetCTL, self).__init__()
        
    def start(self, network):
        print("netctl:: start " + network)
        subprocess.call(["netctl", "start", network])
    
    def stop(self, network):
        print("netctl:: stop " + network)
        subprocess.call(["netctl", "stop", network])
        
    def stopall(self):
        print("netctl:: stop-all")
        subprocess.call(["netctl", "stop-all"])

    def restart(self, network):
        print("netctl:: restart" + network)
        subprocess.call(["netctl", "restart", profile])

class InterfaceCtl(object):
    # Control the network interface, a.k.a wlan0 or eth0
    # etc...

    def __init__(self):
        super(InterfaceCtl, self).__init__()

    def down(self, interface):
        print("interface:: down: " + interface)
        subprocess.call(["ip", "link", "set", "down", "dev", interface])

    def up(self, interface):
        print("interface:: up: " + interface)
        subprocess.call(["ip", "link", "set", "down", "dev", interface])

def CreateConfig(name, interface, security, key=None, ip='dhcp'):
    print("Creating Config File! Don't interrupt!\n")
    filename = "netgui-" + name
    f = open(conf_dir + filename, 'w')
    f.write("# This is the description of the profile. Feel free to change if you want.\n" +
            "Description='This profile was generated by netgui for " + str(name)+".\n" +
            "# The Interface. Do not change, or the profile will not work.\n" +
            "Interface=" + str(interface) + "\n" +
            "#The connection type. Do not change, or it will no longer work.\n" +
            "Connection=wireless\n" +
            "#The security type. Only change if you have personally changed the security type.\n" +
            "Security=" + str(security) + "\n" +
            "#The SSID of the network. Only change if you have personally changed it recently.\n" +
            "ESSID='" + str(name) + "\n")
    if key:
        f.write("#This is the password for your network. Only change if you recently changed it.\n" +
        r'Key=\"' + key + "\n")
    else:
        f.write("#You didn't have security. We recommend changing that. Add some please.\n" +
                r'Key=None\n')
    f.write("#Currently, netgui only support DHCP connection. This will change in later versions\nIP=dhcp\n")
    f.close()
    
def IsConnected():
    # If we are connected to a network, it lists it. Otherwise, it returns nothing (or an empty byte).
    check = subprocess.check_output("netctl list | sed -n 's/^\* //p'", shell=True)
    if check == b'':
        return False
    else:
        return True
    
def CheckOutput(self, command):
    # Run a command, return what it's output was, and convert it from bytes to unicode
    p = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
    output = p.communicate()[0]
    output = output.decode("utf-8")  
    return output

def CheckGrep(self, grepCmd):
    # Run a grep command, decode it from bytes to unicode, strip it of spaces, 
    # and return it's output.
    p = subprocess.Popen(grepCmd, stdout=subprocess.PIPE, shell=True)
    output = ((p.communicate()[0]).decode("utf-8")).strip()
    return output   


def cleanup():
    # Clean up time
    fcntl.lockf(fp, fcntl.LOCK_UN)
    fp.close()
    os.unlink(pidFile)
    try:
        os.unlink(iwlistFile)
        os.unlink(iwconfigFile)
    except:
        pass

if __name__ == "__main__":
    cleanup()
    Gdk.threads_init()
    Gdk.threads_enter()
    netgui()
    Gdk.threads_leave()
    Gtk.main()
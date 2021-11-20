'''TB Animation Tools is a toolset for animators

*******************************************************************************
    License and Copyright
    Copyright 2020-Tom Bailey
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Lesser General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

    send issues/ requests to brimblashman@gmail.com
    visit https://tbanimtools.blogspot.com/ for "stuff"


*******************************************************************************
'''
import pymel.core as pm
import maya.mel as mel
import pymel.core.datatypes as dt
import os
from functools import partial
import maya.OpenMayaUI as omUI
import getStyleSheet as getqss
import json
from Abstract import *
from tb_UI import *

defaultToStandardAtDeadEndOption = 'defaultToStandardAtDeadEndOption'

saveOnUpdateOption = 'tbPickwalkSaveOnUpdate'

getStylesheet = getqss.getStyleSheet()

ToolTip_ctrlClickSelect = 'ctrl + click to select control in scene'
ToolTip_destinationPicker = 'ctrl + click to set from sceme selection' \
                            '\n\tMultiple objects will be added as a new contextual destination. \nshift + click to select currently highlighted destination'
ToolTip_DestinationCtrlClickSet = 'ctrl + click to load destination info'
ToolTip_QuickLeftRight = 'Quick add looping left/right pickwalk'
ToolTip_DownUp = 'Quick add down/up pickwalk, last control ends on self'
ToolTip_DownMulti = 'Quick add down from one object to many (e.g. Hand to Finger controls)\n First selection is the control, others are the destination'
ToolTip_UpMulti = 'Quick add up from many to one (e.g. Finger controls to hand)\n First control is the destination'
ToolTip_AddRigToMap = 'Select a map from the pickwalk map list to assign a rig file to it'

qtVersion = pm.about(qtVersion=True)
if int(qtVersion.split('.')[0]) < 5:
    from PySide.QtGui import *
    from PySide.QtCore import *
    # from pysideuic import *
    from shiboken import wrapInstance
else:
    from PySide2.QtWidgets import *
    from PySide2.QtGui import *
    from PySide2.QtCore import *
    # from pyside2uic import *
    from shiboken2 import wrapInstance

walkDirections = ['up', 'down', 'left', 'right']
skipDirections = ['upSkip', 'downSkip', 'leftSkip', 'rightSkip']

lockedIcon = 'nodeGrapherLocked.png'
unlockedIcon = 'nodeGrapherUnlocked.png'
btnWidth = 80


class WalkData(object):
    """
    Stores all information about pickwalking
    """

    def __init__(self):
        self.name = None
        self._filePath = None
        self.objectDict = dict()
        self.destinations = dict()
        self.jsonObjectInfo = dict()
        self.categoryKeys = dict()

    def __setitem__(self, key, value):
        self.__dict__[key] = value

    def __getitem__(self, key):
        return self.__dict__[key]

    def toJson(self):
        jsonData = '''{}'''
        self.jsonObjectInfo = json.loads(jsonData)
        self.jsonObjectInfo['destinations'] = {key: value.toJson() for key, value in self.destinations.items()}
        self.jsonObjectInfo['objectDict'] = {key.split(':')[-1]: value.toJson() for key, value in
                                             self.objectDict.items()}
        self.jsonObjectInfo['categoryKeys'] = {key: value for key, value in self.categoryKeys.items()}

    def save(self, filePath):
        """

        :return:
        """
        self._filePath = filePath
        self.setName(filePath)
        self.toJson()
        fileName = os.path.join(filePath)
        jsonString = json.dumps(self.jsonObjectInfo, indent=4, separators=(',', ': '))
        jsonFile = open(fileName, 'w')

        jsonFile.write(jsonString)
        jsonFile.close()

    def setName(self, filePath):
        name = filePath.split('/')[-1].split('.')[0]
        name = name.split('\\')[-1]
        self.name = name

    def setLastUsedIndex(self, node):
        for key, value in self.destinations.items():
            if node in value.destination:
                self.destinations[key]._lastIndex = value.destination.index(node)
            elif node in value.destinationAlt:
                self.destinations[key]._lastIndex = value.destinationAlt.index(node)

    def walk(self, namespace=str(), node=str(), direction=str()):
        # do a check on walk for current object in any destination objects, set the appropriate index
        if node not in self.objectDict.keys():
            return None
        target = self.objectDict[node][direction]
        self.setLastUsedIndex(node)
        if target in self.destinations.keys():
            # destination is a conditional destination

            conditionTest = False
            if self.destinations[target].conditionAttribute:
                conditionTest = cmds.getAttr(namespace + self.destinations[target].conditionAttribute) >= \
                                self.destinations[target].conditionValue
            if conditionTest:
                target = self.destinations[target].destinationAlt[self.destinations[target]._lastIndex]
            else:
                target = self.destinations[target].destination[self.destinations[target]._lastIndex]
            return target
            # check for condition attr/object?
            # conditions met, pick alt/destination, use last used index
            pass
        else:
            # destination is an object
            return target
        return None


class PickwalkCreator(object):
    destKey = '_dest'

    ''' Acceptable directions as keys, opposite direction as value for mirroring'''
    directionsDict = {'up': 'up',
                      'down': 'down',
                      'left': 'right',
                      'right': 'left'}
    reciprocalDirectionsDict = {'up': 'down',
                                'down': 'up',
                                'left': 'right',
                                'right': 'left'}

    def __init__(self, namespace=str()):
        self.namespace = namespace

        self.walkData = WalkData()
        self._processedMirrorDestinations = list()  # used when mirroring to prevent looping of recursive function?

    def validForMirror(self, input, sideList):
        for s in sideList:
            if s in input:
                return True
        return False

    def getMirrorName(self, input, sideList):
        for s in sideList:
            if s in input:
                return input.replace(s, sideList[not sideList.index(s)])
        return input

    def addControl(self, control):
        control = control.split(':')[-1]
        if control not in self.walkData.objectDict.keys():
            self.walkData.objectDict[control] = WalkDirectionDict()

    def addDestination(self,
                       name=str(),
                       destination=list(),
                       destinationAlt=list(),
                       conditionAttribute=str(),
                       conditionValue=0.5):
        self.walkData.destinations[name] = WalkDatinationInfo(destination=destination,
                                                              destinationAlt=destinationAlt,
                                                              conditionAttribute=conditionAttribute,
                                                              conditionValue=conditionValue)

    def mirror(self, item, sideList=list()):
        """
        duplicates input and mirrors side info
        if any destinations are conditional, build those as well
        :param item:
        :return:
        """
        for key, walkDirection in self.walkData.objectDict.items():
            mirrorDir = dict()
            # print key, item
            if key == item:
                if not self.validForMirror(key, sideList):
                    continue
                for dir, value in walkDirection.__dict__.items():
                    found = False
                    if not value:
                        mirrorDir[dir] = None
                        continue
                    if value in self.walkData.destinations.keys():
                        # recusrively mirror any destination info found here
                        self.mirrorWalkDestination(destinationKey=value, sideList=sideList)
                        # add the mirror key to the destination list, mirror it
                    mirrorDir[dir] = self.getMirrorName(value, sideList)

                mirrorKey = self.getMirrorName(key, sideList)

                for dKey, dValue in mirrorDir.items():
                    self.setControlDestination(mirrorKey,
                                               direction=dKey,
                                               destination=dValue)
                pass

    def mirrorWalkDestination(self, destinationKey=str(), sideList=list(), processed=list()):
        """
        Mirror all the entries in the destination, the the entries are also destinations,
        recursively edit them, hopefully don't get into a loop....
        :param destinationKey:
        :param sideList:
        :param processed:
        :return:
        """

        if destinationKey in processed:
            return processed
        mirrorDestination = None
        mirrorDestinationAlt = None
        mirrorConditionValue = None
        mirrorConditionAttribute = None
        if not self.validForMirror(destinationKey, sideList):
            return processed
        else:
            mirrorDestinationKey = self.getMirrorName(destinationKey, sideList)
        if mirrorDestinationKey in processed:
            return processed
        if self.walkData.destinations[destinationKey].conditionValue:
            mirrorConditionValue = self.walkData.destinations[destinationKey].conditionValue
        if self.walkData.destinations[destinationKey].conditionAttribute:
            mirrorConditionAttribute = self.getMirrorName(
                self.walkData.destinations[destinationKey].conditionAttribute,
                sideList)
        if self.walkData.destinations[destinationKey].destination:
            mirrorDestination = [self.getMirrorName(x, sideList) for x in
                                 self.walkData.destinations[destinationKey].destination]

        if self.walkData.destinations[destinationKey].destinationAlt:
            mirrorDestinationAlt = [self.getMirrorName(x, sideList) for x in
                                    self.walkData.destinations[destinationKey].destinationAlt]

        self.addDestination(
            name=mirrorDestinationKey,
            destination=mirrorDestination,
            destinationAlt=mirrorDestinationAlt,
            conditionAttribute=mirrorConditionAttribute,
            conditionValue=mirrorConditionValue)
        processed.append(mirrorDestinationKey)
        processed.append(destinationKey)
        for destination in self.walkData.destinations[destinationKey].destination:
            if destination in self.walkData.destinations.keys():
                processed = self.mirrorWalkDestination(destinationKey=destination, sideList=sideList,
                                                       processed=processed)
        for altDestination in self.walkData.destinations[destinationKey].destinationAlt:
            if altDestination in self.walkData.destinations.keys():
                processed = self.mirrorWalkDestination(destinationKey=altDestination, sideList=sideList,
                                                       processed=processed)
        return processed

    def replaceDestination(self, original=str, new=str):
        """
        replaces all occurrences of original with new
        :param original:
        :param new:
        :return:
        """
        for walkDirection in self.walkData.objectDict.values():
            for dir, value in walkDirection.__dict__.items():
                if value == original:
                    walkDirection.__dict__[dir] = new

    def setControlDestination(self, control,
                              direction=str(),
                              destination=str()):
        # add control entry in case it is not already there
        control = str(control).split(':')[-1]
        self.addControl(control)
        destination = destination.split(':')[-1]
        if destination in self.walkData.destinations.keys():
            self.walkData.objectDict[control][direction] = destination
        else:
            # destination is probably one object, just set it as a string
            self.walkData.objectDict[control][direction] = destination

    def addPickwalkChain(self,
                         controls=list(),
                         direction=str(),
                         loop=False,
                         reciprocate=True,
                         endOnSelf=False):
        if not controls:
            return cmds.error('no nodes defined for walk')
        if not isinstance(controls, list):
            controls = [controls]
        controls = [c.split(':')[-1] for c in controls]
        reciprocalIndexes = [None] * len(controls)
        destinationIndexes = [None] * len(controls)
        # get the corresponding walk indexes
        for index, value in enumerate(controls):
            # if this is the last index, pick to loop or not
            if index == (len(controls) - 1):
                if loop:
                    destinationIndexes[index] = (index + 1) % len(controls)

                elif endOnSelf:
                    # not looping so set the node to end at this object
                    destinationIndexes[index] = index
            else:
                destinationIndexes[index] = index + 1
            # get reciprocal indexes
            if index == 0:
                if loop:
                    reciprocalIndexes[index] = len(controls) - 1
            else:
                reciprocalIndexes[index] = index - 1

        infoNodes = [None] * len(controls)
        for index, value in enumerate(controls):
            infoNodes[index] = value

        for index, value in enumerate(controls):
            # get the next index and connect it up to this if reciprocating
            if destinationIndexes[index] is not None:
                self.setControlDestination(value,
                                           direction=direction,
                                           destination=infoNodes[destinationIndexes[index]])
        if reciprocate:
            for index, value in enumerate(reciprocalIndexes):
                if value is not None:
                    self.setControlDestination(controls[index],
                                               direction=self.reciprocalDirectionsDict[direction],
                                               destination=infoNodes[value])

    def getNodeInfoFromRig(self, control):
        """
        Used to grab info from existing message/string attributes on a rig and dump them
        into the walk data
        :param control:
        :return:
        """
        controlName = control.split(':')[-1]
        self.addControl(controlName)
        userAttrs = cmds.listAttr(control, userDefined=True)
        if not userAttrs:
            return
        userAttrs = set(userAttrs)
        for direction, values in Pickwalk().pickwalkAttributeNames.items():
            matching = set(values) & userAttrs
            for m in matching:
                attrType = cmds.getAttr(control + '.' + m, type=True)
                destination = None
                if attrType == 'message':
                    destination = cmds.listConnections(control + '.' + m, source=True, destination=False)
                elif attrType == 'string':
                    destination = cmds.getAttr(control + '.' + m)
                if destination:
                    if isinstance(destination, list):
                        if len(destination) > 1:
                            self.addDestination(
                                name=controlName + '_in',
                                destination=[d.split(':')[-1] for d in destination])
                            continue
                        else:
                            destination = destination[0]
                    self.walkData.objectDict[controlName][direction] = destination.split(':')[-1]

    """ multi object modes etc, called from popups and ui """

    def quickUpFromMulti(self):
        sel = cmds.ls(selection=True, type='transform')
        if not sel:
            return pm.warning('No objects selected')
        if len(sel) > 1:
            # pm.warning('inputSignal_quickUpFromMulti')
            control = sel[0].split(':')[-1]
            targets = [s.split(':')[-1] for s in sel[1:]]
            for s in targets:
                self.setControlDestination(s,
                                           direction='up',
                                           destination=control)

    def quickDownToMulti(self):
        sel = cmds.ls(selection=True, type='transform')
        if not sel:
            return pm.warning('No objects selected')
        if len(sel) > 1:
            # pm.warning('inputSignal_quickDownToMulti')
            control = sel[0].split(':')[-1]
            targets = [s.split(':')[-1] for s in sel[1:]]
            name = control + '_' + targets[0] + '_mult'
            self.addDestination(name=name,
                                destination=targets,
                                destinationAlt=list(),
                                conditionAttribute=str(),
                                conditionValue=0.5)
            self.setControlDestination(control,
                                       direction='down',
                                       destination=name)
            return

    def quickLeftRight(self):
        sel = cmds.ls(selection=True, type='transform')
        if not sel:
            return pm.warning('No objects selected')
        if len(sel) > 1:
            # pm.warning('inputSignal_quickLeftRight')
            self.addPickwalkChain(controls=sel,
                                  direction='left',
                                  loop=True,
                                  reciprocate=True,
                                  endOnSelf=False)
            return

    def quickUpDown(self):
        sel = cmds.ls(selection=True, type='transform')
        if not sel:
            return pm.warning('No objects selected')
        if len(sel) > 1:
            # pm.warning('inputSignal_quickUpDown')
            self.addPickwalkChain(controls=sel,
                                  direction='down',
                                  loop=False,
                                  reciprocate=True,
                                  endOnSelf=True)
            return

    def load(self, walkDataFile, controlFilter=list()):
        """
        Load the walk data file and rebuild the walk info
        :param walkDataFile:
        :return:
        """
        # TODO - move this entirely to the WalkData class?

        filter = False
        try:
            jsonObjectInfo = json.load(open(walkDataFile))
        except ValueError:  # includes simplejson.decoder.JSONDecodeError
            jsonData = '''{}'''
            jsonObjectInfo = json.loads(jsonData)

        if len(controlFilter):
            # strip namespace
            controlFilter = [c.split(':')[-1] for c in controlFilter]
            allDestinations = list()
            for key, value in jsonObjectInfo['objectDict'].items():
                if key not in controlFilter:
                    jsonObjectInfo['objectDict'].pop(key)
                allDestinations.append(value)
            for key, destination in jsonObjectInfo['destinations'].items():
                if key not in allDestinations:
                    jsonObjectInfo['destinations'].pop(key)
        for key, destination in jsonObjectInfo['destinations'].items():
            self.addDestination(name=key,
                                destination=destination['destination'],
                                destinationAlt=destination['destinationAlt'],
                                conditionAttribute=destination['conditionAttribute'],
                                conditionValue=destination['conditionValue'])


        for key, value in jsonObjectInfo['objectDict'].items():
            self.addControl(key)
            for dKey, dValue in value.items():
                self.setControlDestination(key,
                                           direction=dKey,
                                           destination=dValue)

        self.walkData._filePath = walkDataFile
        self.walkData.setName(walkDataFile)

class hotkeys(hotKeyAbstractFactory):
    def createHotkeyCommands(self):
        self.setCategory(self.helpStrings.category.get('pickwalk'))
        self.commandList = list()
        self.addCommand(self.tb_hkey(name='tbOpenPickwalkCreator',
                                     annotation='OpenPickwalkCreator',
                                     category=self.category,
                                     command=['Pickwalk.openCreator()'],
                                     help=self.helpStrings.OpenPickwalkCreator))
        self.addCommand(self.tb_hkey(name='tbOpenPickwalkLibrary',
                                     annotation='OpenPickwalkLibrary',
                                     category=self.category,
                                     command=['Pickwalk.openLibrary()'],
                                     help=self.helpStrings.OpenPickwalkLibrary))
        self.addCommand(self.tb_hkey(name='tbPickwalkUp',
                                     annotation='pickwalk up, defaults to message attrs, then standard maya function',
                                     category=self.category,
                                     command=['Pickwalk.walkUp()']))
        self.addCommand(self.tb_hkey(name='tbPickwalkDown',
                                     annotation='pickwalk down, defaults to message attrs, then standard maya function',
                                     category=self.category,
                                     command=['Pickwalk.walkDown()']))
        self.addCommand(self.tb_hkey(name='tbPickwalkLeft',
                                     annotation='pickwalk left, defaults to message attrs, then standard maya function',
                                     category=self.category,
                                     command=['Pickwalk.walkLeft()']))
        self.addCommand(self.tb_hkey(name='tbPickwalkRight',
                                     annotation='pickwalk right, defaults to message attrs, then standard maya function',
                                     category=self.category,
                                     command=['Pickwalk.walkRight()']))

        self.addCommand(self.tb_hkey(name='tbPickwalkUpAdd',
                                     annotation='pickwalk up add, defaults to message attrs, then standard maya function',
                                     category=self.category,
                                     command=['Pickwalk.walkUpAdd()']))
        self.addCommand(self.tb_hkey(name='tbPickwalkDownAdd',
                                     annotation='pickwalk down add, defaults to message attrs, then standard maya function',
                                     category=self.category,
                                     command=['Pickwalk.walkDownAdd()']))
        self.addCommand(self.tb_hkey(name='tbPickwalkLeftAdd',
                                     annotation='pickwalk left add, defaults to message attrs, then standard maya function',
                                     category=self.category,
                                     command=['Pickwalk.walkLeftAdd()']))
        self.addCommand(self.tb_hkey(name='tbPickwalkRightAdd',
                                     annotation='pickwalk right add, defaults to message attrs, then standard maya function',
                                     category=self.category,
                                     command=['Pickwalk.walkRightAdd()']))

        self.addCommand(self.tb_hkey(name='tbPickwalkUpCreate',
                                     annotation='Create a new pickwalk, raise the ui if needed',
                                     category=self.category,
                                     command=["Pickwalk.walkCreate('up', condition=False)"]))
        self.addCommand(self.tb_hkey(name='tbPickwalkDownCreate',
                                     annotation='Create a new pickwalk, raise the ui if needed',
                                     category=self.category,
                                     command=["Pickwalk.walkCreate('down', condition=False)"]))
        self.addCommand(self.tb_hkey(name='tbPickwalkLeftCreate',
                                     annotation='Create a new pickwalk, raise the ui if needed',
                                     category=self.category,
                                     command=["Pickwalk.walkCreate('left', condition=False)"]))
        self.addCommand(self.tb_hkey(name='tbPickwalkRightCreate',
                                     annotation='Create a new pickwalk, raise the ui if needed',
                                     category=self.category,
                                     command=["Pickwalk.walkCreate('right', condition=False)"]))

        self.addCommand(self.tb_hkey(name='tbPickwalkUpCreateCondition',
                                     annotation='Create a new pickwalk, raise the ui if needed',
                                     category=self.category,
                                     command=["Pickwalk.walkCreate('up', condition=True)"]))
        self.addCommand(self.tb_hkey(name='tbPickwalkDownCreateCondition',
                                     annotation='Create a new pickwalk, raise the ui if needed',
                                     category=self.category,
                                     command=["Pickwalk.walkCreate('down', condition=True)"]))
        self.addCommand(self.tb_hkey(name='tbPickwalkLeftCreateCondition',
                                     annotation='Create a new pickwalk, raise the ui if needed',
                                     category=self.category,
                                     command=["Pickwalk.walkCreate('left', condition=True)"]))
        self.addCommand(self.tb_hkey(name='tbPickwalkRightCreateCondition',
                                     annotation='Create a new pickwalk, raise the ui if needed',
                                     category=self.category,
                                     command=["Pickwalk.walkCreate('right', condition=True)"]))

        return self.commandList

    def assignHotkeys(self):
        return pm.warning(self, 'assignHotkeys', ' function not implemented')


class Pickwalk(toolAbstractFactory):
    """
    Use this as a base for toolAbstractFactory classes
    """
    # __metaclass__ = abc.ABCMeta
    __instance = None
    toolName = 'Pickwalk'
    libraryName = 'pickwalkLibraryData'
    subfolder = 'pickwalkData'
    dataPath = None
    defaultPickwalkDir = None
    hotkeyClass = None
    funcs = None

    saveOnUpdateOption = saveOnUpdateOption
    defaultToStandardAtDeadEndOption = defaultToStandardAtDeadEndOption

    transformTranslateDict = dict()
    transformRotateDict = dict()

    walkDataLibrary = str()
    pickwalkData = dict()
    rigToWalkDataDict = dict()

    walkDirectionNames = {'up': 'pickUp',
                          'down': 'pickDown',
                          'left': 'pickLeft',
                          'right': 'pickRight',
                          }

    pickwalkAttributeNames = {'up': [walkDirectionNames['up'],
                                     '_pickwalk_up',
                                     'cgTkPickWalkup',
                                     'zooWalkup'],
                              'down': [walkDirectionNames['down'],
                                       '_pickwalk_down',
                                       'cgTkPickWalkdown',
                                       'zooWalkdown'],
                              'left': [walkDirectionNames['left'],
                                       '_pickwalk_left',
                                       'cgTkPickWalkleft',
                                       'zooWalkleft'],
                              'right': [walkDirectionNames['right'],
                                        '_pickwalk_right',
                                        'cgTkPickWalkright',
                                        'zooWalkright'],
                              }
    melCommands = {'up': 'pickWalkUp',
                   'down': 'pickWalkDown',
                   'left': 'pickWalkLeft',
                   'right': 'pickWalkRight',
                   }

    walkHotkeyMap = {'up': 'tbPickwalkUp',
                     'down': 'tbPickwalkDown',
                     'left': 'tbPickwalkLeft',
                     'right': 'tbPickwalkRight',
                     }
    walkAddHotkeyMap = {'up': 'tbPickwalkUpAdd',
                        'down': 'tbPickwalkDownAdd',
                        'left': 'tbPickwalkLeftAdd',
                        'right': 'tbPickwalkRightAdd',
                        }

    walkCreateHotkeyMap = {'up': 'tbPickwalkUpCreate',
                           'down': 'tbPickwalkDownCreate',
                           'left': 'tbPickwalkLeftCreate',
                           'right': 'tbPickwalkRighCreate',
                           }
    walkCreateConditionHotkeyMap = {'up': 'tbPickwalkUpCreateCondition',
                                    'down': 'tbPickwalkDownCreateCondition',
                                    'left': 'tbPickwalkLeftCreateCondition',
                                    'right': 'tbPickwalkRightCreateCondition',
                                    }
    WASDwalkHotkeyMap = {'w': 'tbPickwalkUp',
                         's': 'tbPickwalkDown',
                         'a': 'tbPickwalkLeft',
                         'd': 'tbPickwalkRight',
                         }

    pickwalkCreator = PickwalkCreator()

    def __new__(cls):
        if Pickwalk.__instance is None:
            Pickwalk.__instance = object.__new__(cls)

        Pickwalk.__instance.val = cls.toolName
        Pickwalk.__instance.initData()
        Pickwalk.__instance.loadWalkLibrary()
        Pickwalk.__instance.getAllPickwalkMaps()
        Pickwalk.__instance.initialiseWalkData()
        return Pickwalk.__instance

    def __init__(self):
        self.hotkeyClass = hotkeys()
        self.funcs = functions()
        self.initData()

    def initData(self):
        super(Pickwalk, self).initData()
        self.defaultPickwalkDir = os.path.normpath(os.path.join(self.dataPath, self.subfolder))
        if not os.path.isdir(self.defaultPickwalkDir):
            os.mkdir(self.defaultPickwalkDir)

    """
    Declare an interface for operations that create abstract product
    objects.
    """

    def optionUI(self):
        super(Pickwalk, self).optionUI()
        # self.widget.setGeometry(600, 100, 1000, 900)
        openLibrary = QPushButton('Open Pickwalk library')
        openLibrary.clicked.connect(self.openLibrary)
        self.layout.addWidget(openLibrary)

        openCreator = QPushButton('Open Pickwalk creator')
        openCreator.clicked.connect(self.openCreator)
        self.layout.addWidget(openCreator)

        endOptionWidget = optionVarBoolWidget('Default to standard walk on empty custom map ',
                                              self.defaultToStandardAtDeadEndOption)
        self.layout.addWidget(endOptionWidget)

        layout = QHBoxLayout()
        arrowLabel = QLabel('Arrow keys for pickwalking')
        assignArrowHotkeys = QPushButton('Assign arrow keys')
        assignArrowHotkeys.clicked.connect(self.assignArrowHotkeys)
        layout.addWidget(assignArrowHotkeys)
        layout.addWidget(arrowLabel)
        self.layout.addLayout(layout)

        layout = QHBoxLayout()
        shiftArrowLabel = QLabel('Shift+Alt WASD for pickwalking')
        assignWASDHotkeys = QPushButton('Assign ShiftAlt + WASD keys')
        assignWASDHotkeys.clicked.connect(self.assignWASDHotkeys)
        layout.addWidget(assignWASDHotkeys)
        layout.addWidget(shiftArrowLabel)
        self.layout.addLayout(layout)

        layout = QHBoxLayout()
        WASDLabel = QLabel('Shift arrow keys for additive pickwalking')
        assignArrowHotkeys = QPushButton('Assign shift + arrow keys')
        assignArrowHotkeys.clicked.connect(self.assignShiftArrowHotkeys)
        layout.addWidget(assignArrowHotkeys)
        layout.addWidget(WASDLabel)
        self.layout.addLayout(layout)

        layout = QHBoxLayout()
        ctrlArrowLabel = QLabel('Ctrl arrow keys for pickwalk creation')
        assignArrowHotkeys = QPushButton('Assign ctrl + arrow keys')
        assignArrowHotkeys.clicked.connect(self.assignCtrlArrowHotkeys)
        layout.addWidget(assignArrowHotkeys)
        layout.addWidget(ctrlArrowLabel)
        self.layout.addLayout(layout)

        layout = QHBoxLayout()
        ctrlShiftrrowLabel = QLabel('Ctrl shift arrow keys for conditional pickwalk creation')
        assignArrowHotkeys = QPushButton('Assign ctrl + shift + arrow keys')
        assignArrowHotkeys.clicked.connect(self.assignCtrlShiftArrowHotkeys)
        layout.addWidget(assignArrowHotkeys)
        layout.addWidget(ctrlShiftrrowLabel)
        self.layout.addLayout(layout)

        layout = QHBoxLayout()
        revertArrowLabel = QLabel('Revert Arrow keys to default')
        revertArrowHotkeys = QPushButton('Revert')
        revertArrowHotkeys.clicked.connect(self.revertArrowHotkeys)
        layout.addWidget(revertArrowHotkeys)
        layout.addWidget(revertArrowLabel)
        self.layout.addLayout(layout)


        self.layout.addStretch()
        return self.optionWidget

    def showUI(self):
        return cmds.warning(self, 'optionUI', ' function not implemented')

    def drawMenuBar(self, parentMenu):
        pm.menuItem(label='Pickwalk Creator', image='walk.png', command='tbOpenPickwalkCreator', sourceType='mel',
                    parent=parentMenu)
        pm.menuItem(label='Pickwalk Library', image='QR_settings.png', command='tbOpenPickwalkLibrary',
                    sourceType='mel', parent=parentMenu)

    def openLibrary(self):
        win = pickwalkRigAssignemtWindow()
        win.show()

    def openCreator(self):
        win = pickwalkMainWindow()
        win.show()

    def revertArrowHotkeys(self):
        pass

    def assignArrowHotkeys(self):
        for direction, command in self.walkHotkeyMap.items():
            cmds.hotkey(keyShortcut=direction,
                        name=command + 'NameCommand')

    def assignShiftArrowHotkeys(self):
        for direction, command in self.walkAddHotkeyMap.items():
            cmds.hotkey(keyShortcut=direction,
                        shiftModifier=True,
                        name=command + 'NameCommand')

    def assignCtrlArrowHotkeys(self):
        for direction, command in self.walkAddHotkeyMap.items():
            cmds.hotkey(keyShortcut=direction,
                        shiftModifier=False,
                        ctrltModifier=True,
                        name=command + 'NameCommand')

    def assignCtrlShiftArrowHotkeys(self):
        for direction, command in self.walkCreateHotkeyMap.items():
            cmds.hotkey(keyShortcut=direction,
                        shiftModifier=True,
                        ctrltModifier=True,
                        name=command + 'NameCommand')

    def assignWASDHotkeys(self):
        for direction, command in self.walkCreateConditionHotkeyMap.items():
            cmds.hotkey(keyShortcut=direction,
                        shiftModifier=True,
                        altModifier=True,
                        name=command + 'NameCommand')

    def loadWalkLibrary(self):
        self.libraryFile = self.libraryName + '.json'
        self.libraryFilePath = os.path.join(self.defaultPickwalkDir, self.libraryFile)

        if not os.path.isfile(self.libraryFilePath):
            self.walkDataLibrary = WalkDataLibrary()
            self.savePickwalkLibraryMap()
        else:
            self.walkDataLibrary = WalkDataLibrary()
            self.walkDataLibrary.load(self.libraryFilePath)

        for key, values in self.walkDataLibrary.rigMapDict.items():
            for v in values:
                self.rigToWalkDataDict[v] = key
        return self.walkDataLibrary

    def getAllPickwalkMaps(self):
        self.jsonFiles = list()
        for filename in os.listdir(self.defaultPickwalkDir):
            if filename.endswith(".json"):
                if os.path.basename(filename) == self.libraryFile:
                    continue
                self.jsonFiles.append(os.path.join(self.defaultPickwalkDir, filename))
        for filename in self.jsonFiles:
            mapName = os.path.basename(filename).split('.')[0]
            if mapName not in self.walkDataLibrary.rigMapDict.keys():
                self.walkDataLibrary.rigMapDict[mapName] = list()

        statinfo = os.access(self.libraryFilePath, os.W_OK)
        if statinfo:
            self.savePickwalkLibraryMap()

    def initialiseWalkData(self):
        """
        Load up all the pickwalk maps into a big dictionary
        :return:
        """
        for walkData in self.jsonFiles:
            mapName = os.path.basename(walkData).split('.')[0]
            jsonObjectInfo = json.load(open(walkData))

            pickwalkCreator = PickwalkCreator()
            pickwalkCreator.load(walkData)
            self.pickwalkData[mapName] = pickwalkCreator.walkData

    def walkStandard(self, direction):
        mel.eval(self.melCommands[direction])

    def pickWalkAttribute(self, node=None, attribute=None):
        # check if message attribute exists
        if not cmds.attributeQuery(attribute, node=node, exists=True):
            return
        # walk attribute exists, check it's type
        if cmds.getAttr(node + '.' + attribute, type=True) == u'string':
            # use string attribute method
            destination = cmds.getAttr(node + '.' + attribute)
            pNode = pm.PyNode(node)
            if cmds.objExists(pNode.namespace() + cmds.getAttr(node + '.' + attribute)):
                return pNode.namespace() + destination

        elif cmds.getAttr(node + '.' + attribute, type=True) == u'message':
            # list connection to message attribute
            conns = cmds.listConnections(node + '.' + attribute, source=True, destination=False)
            # if there are connections, check what kind of node it is
            if conns:
                return conns[0]

    def walkCreate(self, direction=str(), condition=False):
        sel = cmds.ls(sl=True, type='transform')
        returnedControls = list()
        if not sel:
            return
        if direction not in self.walkDirectionNames.keys():
            return cmds.error('\nInvalid pick direction, only up, down, left, right are supported')

        self.loadLibraryForCurrent()

        if not condition:
            if len(sel) == 1:
                sel.append(sel[0])
            if len(sel) == 2:
                # 2 objects - create single direction pickwalk
                self.pickwalkCreator.setControlDestination(sel[0],
                                                           direction=direction,
                                                           destination=sel[1])
                if direction != 'up':
                    # if left or right, create the reverse
                    self.pickwalkCreator.setControlDestination(sel[1],
                                                               direction=self.pickwalkCreator.reciprocalDirectionsDict[direction],
                                                               destination=sel[0])
            elif len(sel) > 2:
                # add all objects in a chain
                self.pickwalkCreator.addPickwalkChain(
                    controls=sel,
                    direction=direction,
                    loop=direction == 'left' or direction == 'right',
                    reciprocate=True,
                    endOnSelf=direction == 'down')
        else:
            if len(sel) == 1 or len(sel) == 2:
                dlg = PickwalkPopup()
                dlg.show()
            else:
                if direction == 'down':
                    self.pickwalkCreator.quickDownToMulti()
                elif direction == 'up':
                    self.pickwalkCreator.quickUpFromMulti()
        self.saveLibrary()
        self.forceReloadData()
        return

    def pickwalk(self, direction=str, add=False):
        sel = pm.ls(sl=True, type='transform')
        returnedControls = list()
        if not sel:
            self.walkStandard(direction)
            return

        walkObject = sel[-1]
        if direction not in self.walkDirectionNames.keys():
            return cmds.error('\nInvalid pick direction, only up, down, left, right are supported')

        refName = self.getRefName(walkObject)
        if refName:
            returnedControls = self.dataDrivenWalk(direction, refName, walkObject)
            if returnedControls == False:
                # means a standard walk has been performed
                return

        if not returnedControls:
            # anything beyond here is using attribute based pickwalking
            userAttrs = cmds.listAttr(str(walkObject), userDefined=True)
            if not userAttrs:
                self.walkStandard(direction)
                return
            pickAttributes = [i for i in self.pickwalkAttributeNames[direction] if i in userAttrs]
            if not pickAttributes:
                # didn't find any custom pickwalk attributes, use the regular walk
                self.walkStandard(direction)
                return

            found = False

            for walkAttribute in self.pickwalkAttributeNames[direction]:
                if not found:
                    if cmds.attributeQuery(walkAttribute, node=str(walkObject), exists=True):
                        returnObj = self.pickWalkAttribute(node=str(walkObject), attribute=walkAttribute)
                        if returnObj:
                            if isinstance(returnObj, list):
                                returnedControls.extend(returnObj)
                                found = True
                            else:
                                returnedControls.append(returnObj)
                                found = True

        if not returnedControls:
            self.walkStandard(direction)
            return
        if add:
            cmds.select([str(s) for s in sel] + returnedControls, replace=True)
            return
        cmds.select(returnedControls, replace=True)

    def getRefName(self, walkObject):
        refName = None
        refState = cmds.referenceQuery(str(walkObject), isNodeReferenced=True)
        if refState:
            # if it is referenced, check against pickwalk library entries
            refName = cmds.referenceQuery(str(walkObject), filename=True, shortName=True).split('.')[0]
        else:
            # might just be working in the rig file itself
            refName = cmds.file(query=True, sceneName=True, shortName=True).split('.')[0]
        return refName

    def dataDrivenWalk(self, direction, refName, walkObject):
        returnedControls = list()
        walkObjectStripped = walkObject.stripNamespace()
        walkObjectNS = walkObject.namespace()
        userAttrs = cmds.listAttr(str(walkObject), userDefined=True)
        if refName in self.walkDataLibrary._fileToMapDict.keys():
            mapName = self.walkDataLibrary._fileToMapDict[refName]
            result = self.pickwalkData[mapName].walk(namespace=walkObjectNS,
                                                     node=walkObjectStripped,
                                                     direction=direction)
            if result is u'(None,)':
                self.pickNewDestination(direction, walkObjectNS, walkObjectStripped)
                return False
            if result is None:
                self.pickNewDestination(direction, walkObjectNS, walkObjectStripped)
                return False

            if cmds.objExists(walkObjectNS + result):
                returnedControls.append(walkObjectNS + result)
            else:
                self.pickNewDestination(direction, walkObjectNS, walkObjectStripped)
                if pm.optionVar.get(self.defaultToStandardAtDeadEndOption, True):
                    self.walkStandard(direction)
                    return
                return False
            return returnedControls
        elif refName not in self.walkDataLibrary.ignoredRigs:
            self.queryWalkOnNewRig(refName)
        elif userAttrs:
            pickAttributes = [i for i in self.pickwalkAttributeNames[direction] if i in userAttrs]
            if pickAttributes:
                # exit and return to standard pickwalk ( bit of repeated code but whatever for now )
                print ('Attribute driven pickwalk found', pickAttributes)
                return returnedControls
        return returnedControls

    def pickNewDestination(self, direction, namespace, walkObject):
        prompt = PickWalkObjectDialog(direction, namespace, walkObject, parent=getMainWindow(),
                                      title='No destination found',
                                      text=str("Pick new control for {control} {dir}").format(control=walkObject,
                                                                                              dir=direction))
        prompt.assignSignal.connect(self.assignNewDestinationFromWalk)
        prompt.conditionSignal.connect(self.assignNewConditionFromWalk)
        prompt.show()

    def assignNewConditionFromWalk(self, direction, namespace, walkObject, destination):
        cmds.select(namespace + ':' + walkObject, replace=True)
        self.loadLibraryForCurrent()
        dlg = PickwalkPopup(control=walkObject, destination=destination)
        dlg.show()

    def assignNewDestinationFromWalk(self, direction, namespace, walkObject, destination):
        cmds.select(namespace + ':' + walkObject, replace=True)
        self.loadLibraryForCurrent()
        # TODO - make this work with the incoming list
        self.pickwalkCreator.setControlDestination(walkObject,
                                                   direction=direction,
                                                   destination=destination[0])
        self.saveLibrary()
        self.forceReloadData()

    def forceReloadData(self):
        self.loadLibraryForCurrent()
        self.loadWalkLibrary()
        self.getAllPickwalkMaps()
        self.initialiseWalkData()

    def queryWalkOnNewRig(self, refName):
        prompt = PickwalkQueryWidget(title='New Rig Found', rigName=refName,
                                     text='This rig new, set up pickwalking on it?')
        prompt.AssignNewRigSignal.connect(self.assignNewRigExistingMap)
        prompt.IgnoreRigSignal.connect(self.assignIgnoreNewRig)
        prompt.CreateNewRigMapSignal.connect(self.assignNewRigNewMap)
        if prompt.exec_():
            pass
        else:
            pass

    def walkUp(self):
        self.pickwalk(direction='up')

    def walkDown(self):
        self.pickwalk(direction='down')

    def walkLeft(self):
        self.pickwalk(direction='left')

    def walkRight(self):
        self.pickwalk(direction='right')

    def walkUpAdd(self):
        self.pickwalk(direction='up', add=True)

    def walkDownAdd(self):
        self.pickwalk(direction='down', add=True)

    def walkLeftAdd(self):
        self.pickwalk(direction='left', add=True)

    def walkRightAdd(self):
        self.pickwalk(direction='right', add=True)

    def walkUpCreate(self):
        self.walkCreate(direction='up')

    def walkDownCreate(self):
        self.walkCreate(direction='down')

    def walkLeftCreate(self):
        self.walkCreate(direction='left')

    def walkRightCreate(self):
        self.walkCreate(direction='right')

    def assignNewRigExistingMap(self, rigName):
        prompt = PickListDialog(title='Assign rig to existing map', text='Pick exising pickwalk map for rig',
                                itemList=self.walkDataLibrary.rigMapDict.keys(),
                                rigName=rigName)
        prompt.assignSignal.connect(self.assignRig)
        if prompt.exec_():
            pass
        else:
            pass

    def assignRig(self, rigMap, rigName):
        self.walkDataLibrary.assignRig(rigMap, rigName)
        self.savePickwalkLibraryMap()
        self.getAllPickwalkMaps()

    def savePickwalkLibraryMap(self):
        self.walkDataLibrary.save(self.libraryFilePath)

    def assignIgnoreNewRig(self, rigName):
        self.walkDataLibrary.ignoreRig(rigName)
        self.savePickwalkLibraryMap()
        self.getAllPickwalkMaps()

    def assignNewRigNewMap(self, rigName):
        win = pickwalkMainWindow(autoLoad=False)

        # TODO this is a bit ugly as it opens the save as windows window, nice to avoid that as you have to save
        # TODO the pickwalk map in the save folder anyway
        newMap = win.saveAsLibrary()

        self.walkDataLibrary.assignRig(newMap.split('.')[0], rigName)
        self.savePickwalkLibraryMap()
        self.getAllPickwalkMaps()
        Pickwalk()
        win.show()
        win.loadLibraryForCurrent()

    """
    Functions moved from mainwindow to here
    """

    def getCurrentRig(self):
        refName = None
        mapName = None
        fname = None
        sel = cmds.ls(sl=True)

        if sel:
            refState = cmds.referenceQuery(sel[0], isNodeReferenced=True)
            if refState:
                # if it is referenced, check against pickwalk library entries
                refName = cmds.referenceQuery(sel[0], filename=True, shortName=True).split('.')[0]
            else:
                # might just be working in the rig file itself
                refName = cmds.file(query=True, sceneName=True, shortName=True).split('.')[0]
        else:
            refName = cmds.file(query=True, sceneName=True, shortName=True).split('.')[0]

        if refName in self.walkDataLibrary._fileToMapDict.keys():
            mapName = self.walkDataLibrary._fileToMapDict[refName]
            fname = os.path.join(self.defaultPickwalkDir, mapName + '.json')
        return fname

    def loadLibraryForCurrent(self):
        # TODO - implement this to look at the main walk library and open the
        # TODO - correct map file
        #
        fname = self.getCurrentRig()
        if not fname:
            fname = self.browseToFile()
        if not fname:
            return None

        self.pickwalkCreator.load(fname)

    def browseToFile(self):
        fname = QFileDialog.getOpenFileName(QWidget(), 'Open file',
                                            cmds.workspace(q=True, directory=True),
                                            "Pickwalk files (*.json)")
        return fname[0] or None

    def saveLibrary(self):
        if not self.pickwalkCreator.walkData._filePath:
            self.saveAsLibrary()
            return
        self.pickwalkCreator.walkData.save(self.pickwalkCreator.walkData._filePath)
        self.pickwalkCreator.load(self.pickwalkCreator.walkData._filePath)
        self.loadWalkLibrary()
        self.getAllPickwalkMaps()

    def saveAsLibrary(self):
        save_filename = QFileDialog.getSaveFileName(QWidget(),
                                                    "Save file as",
                                                    self.defaultPickwalkDir,
                                                    "Pickwalk files (*.json)")
        if not save_filename:
            return
        if os.path.isfile(save_filename[0]):
            if self.overwriteQuery().exec_() != 1024:
                return
        self.pickwalkCreator.walkData.save(save_filename[0])
        self.loadWalkLibrary()

        return os.path.basename(save_filename[0])

    def getCurrentLibraryName(self):
        return self.pickwalkCreator.walkData.name

    def overwriteQuery(self):
        msg = QMessageBox()
        msg.setStyleSheet(getqss.getStyleSheet())
        msg.setIcon(QMessageBox.Warning)

        msg.setText("Overwrite existing data?")
        msg.setWindowTitle("Existing file warning")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        return msg


class WalkDataLibrary(object):
    def __init__(self):
        self.rigMapDict = dict()
        self.ignoredRigs = list()
        self._fileToMapDict = dict()
        self._walkData = dict()

    def toJson(self):
        jsonData = '''{}'''
        self.jsonObjectInfo = json.loads(jsonData)
        self.jsonObjectInfo['rigMapDict'] = {key: value for key, value in self.rigMapDict.items()}
        self.jsonObjectInfo['ignoredRigs'] = self.ignoredRigs

    def assignRig(self, mapName, rigName):
        for key, values in self.rigMapDict.items():
            if rigName in values:
                values.remove(rigName)
        if rigName in self.ignoredRigs:
            self.ignoredRigs.remove(rigName)
        self.rigMapDict[mapName].append(rigName)

    def ignoreRig(self, rigName):
        for key, values in self.rigMapDict.items():
            if rigName in values:
                values.remove(rigName)
        if rigName not in self.ignoredRigs:
            self.ignoredRigs.append(rigName)

    def save(self, filePath):
        """
        :return:
        """
        self.name = filePath.split('/')[-1].split('.')[0]
        self.toJson()

        fileName = os.path.join(filePath)
        jsonString = json.dumps(self.jsonObjectInfo, indent=4, separators=(',', ': '))
        jsonFile = open(fileName, 'w')
        jsonFile.write(jsonString)
        jsonFile.close()

        self.createFileToRigMapping()

    def load(self, filepath):
        jsonObjectInfo = json.load(open(filepath))
        self.rigMapDict = jsonObjectInfo['rigMapDict']
        self.ignoredRigs = jsonObjectInfo['ignoredRigs']
        self.createFileToRigMapping()

    def createFileToRigMapping(self):
        for key, values in self.rigMapDict.items():
            for v in values:
                self._fileToMapDict[v] = key


class WalkDirectionDict(object):
    """
    Dictionary of walk directions, entries will be walkDatinationInfo() or str()
    """

    def __init__(self, left=None,
                 right=None,
                 up=None,
                 down=None):
        self.left = left,
        self.right = right,
        self.up = up,
        self.down = down

    def __setitem__(self, key, value):
        self.__dict__[key] = value

    def __getitem__(self, key):
        return self.__dict__[key]

    def toJson(self):
        for key, value in self.__dict__.items():
            if value == u'(None,)':
                value = None
        return {key: str(value).split(':')[-1] for key, value in self.__dict__.items()}


class WalkDatinationInfo(object):
    """
    Stores a particular set of destinations/condition
    """

    def __init__(self, destination=list(),
                 destinationAlt=list(),
                 conditionAttribute=list(),
                 conditionValue=0.5
                 ):
        self.destination = self.stripList(destination)
        self.destinationAlt = self.stripList(destinationAlt)
        self.conditionAttribute = conditionAttribute
        self.conditionValue = conditionValue
        self._lastIndex = 0

    def stripList(self, input):
        if len(input):
            return [x.split(':')[-1] for x in input]
        else:
            return input

    def toJson(self):
        d = dict((key, value) for key, value in self.__dict__.items() if not key.startswith("__"))
        return d


pwShapeWindow = None
pickwalkWorkspaceControlName = 'pwWorkspaceControl'


def getMainWindow():
    return wrapInstance(int(omUI.MQtUtil.mainWindow()), QWidget)


def workspaceScript(*args):
    parentWidget = pm.toQtObject(pm.setParent(q=True))
    parentLayout = filter(lambda c: isinstance(c, QLayout), parentWidget.children())

    global pwShapeWindow

    if 'controlShapeWindow' not in globals():
        pm.mel.evalDeferred(
            'if (`workspaceControl -exists "shapeWorkspaceControl"`) workspaceControl -e -close "shapeWorkspaceControl";')

    if pwShapeWindow:
        try:
            pwShapeWindow.close()
        except:
            pass

    pwShapeWindow = pickwalkMainWindow()
    pwShapeWindow.show()
    parentLayout[0].addWidget(pwShapeWindow)


def dockControl():
    channelBoxTab = pm.mel.eval('getUIComponentDockControl("Channel Box / Layer Editor", false)')
    if pm.workspaceControl(pickwalkWorkspaceControlName, exists=True):
        try:
            pm.deleteUI(pickwalkWorkspaceControlName)
        except:
            pass
    pm.workspaceControl(pickwalkWorkspaceControlName,
                        tabToControl=[channelBoxTab, -1],
                        uiScript='import tb_pickwalk as tbPW;reload(tbPW);tbPW.workspaceScript()',
                        loadImmediately=True,
                        initialWidth=100,
                        # minimumWidth=False,
                        widthProperty='free',
                        retain=False,
                        r=True,
                        label='tbPickWalk')


class standardPickButton(QPushButton):
    pressedSignal = Signal(str)
    direction = str()

    def __init__(self, label=str, direction=str, icon=str(), fixedWidth=False, width=64, rotation=0, *args, **kwargs):
        QPushButton.__init__(self, *args, **kwargs)
        self.setText(label)
        self.direction = direction
        if fixedWidth:
            self.setFixedWidth(width)
        upRotate = QTransform().rotate(rotation)
        pixmap = QPixmap(':/{}'.format(icon)).transformed(upRotate)
        icon = QIcon(pixmap)

        self.setIcon(icon)

        self.clicked.connect(partial(self.pressedSignal.emit, self.direction))


class DirectionPickButton(QWidget):
    pressedSignal = Signal(str, str)
    conditionPressedSignal = Signal(str, str)
    direction = str()

    def __init__(self, mainWindow, loop=False, endOnSelf=False, label=str, direction=str, icon=str(), fixedWidth=False,
                 rotation=0,
                 *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)
        self.mainWindow = mainWindow
        self.direction = direction
        self.mainLayout = QHBoxLayout()
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.mainLayout)
        self.label = QLabel(direction)
        self.label.setFixedWidth(64)
        self.label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self.lineEdit = QLineEdit()
        self.button = standardPickButton(label='from sel', direction=direction, icon=icon,
                                         rotation=rotation, width=32, fixedWidth=False)
        self.contextButton = QPushButton('< from destination list')
        self.mainLayout.addWidget(self.label)
        self.mainLayout.addWidget(self.lineEdit)
        self.mainLayout.addWidget(self.button)
        self.mainLayout.addWidget(self.contextButton)

        self.button.clicked.connect(partial(self.pressedSignal.emit,
                                            self.lineEdit.text(),
                                            self.direction,
                                            ))
        self.contextButton.clicked.connect(partial(self.conditionPressedSignal.emit,
                                                   self.lineEdit.text(),
                                                   self.direction,
                                                   ))
        self.label.setStyleSheet("QLabel {"
                                 "border-width: 0;"
                                 "border-radius: 0;"
                                 "border-style: solid;"
                                 "border-color: #222222}"
                                 )
        self.button.clicked.connect(self.pickControl)
        self.contextButton.clicked.connect(self.pickDestination)

    def pickControl(self):
        sel = pm.ls(selection=True, type='transform')
        if not sel:
            lbl = ''
        if len(sel) > 1:
            pm.warning('need to make this support auto creation of contexts')
            lbl = ''
        else:
            lbl = sel[0].stripNamespace()
        self.lineEdit.setText(lbl)

    def pickDestination(self):
        self.lineEdit.setText(self.mainWindow.currentDestination)


class ChainPickButton(QWidget):
    pressedSignal = Signal(bool, bool)
    direction = str()

    def __init__(self, mainWindow, loop=False, endOnSelf=False, label=str, direction=str, icon=str(), fixedWidth=False,
                 width=32,
                 noOption=False,
                 rotation=0,
                 *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)
        self.mainWindow = mainWindow
        self.loop = loop
        self.direction = direction
        self.mainLayout = QHBoxLayout()
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.mainLayout)
        self.button = standardPickButton(label=label, direction=direction, icon=icon, fixedWidth=fixedWidth,
                                         width=width,
                                         rotation=rotation)

        self.loopCB = LoopCBWidget(loop=loop, label='loop')
        self.endOnSelfCB = LoopCBWidget(loop=endOnSelf, label='end on self')
        self.mainLayout.addWidget(self.button)
        if not noOption:
            self.mainLayout.addWidget(self.loopCB)
            self.mainLayout.addWidget(self.endOnSelfCB)
        else:
            self.mainLayout.addStretch()
        self.button.clicked.connect(partial(self.pressedSignal.emit,
                                            self.loopCB.checkbox.isChecked(),
                                            self.endOnSelfCB.checkbox.isChecked(),
                                            ))


class lockButton(QPushButton):
    pressedSignal = Signal(bool)

    def __init__(self, icon=str(), icon2=str(), *args, **kwargs):
        QPushButton.__init__(self, *args, **kwargs)
        self.lockedIcon = QIcon(QPixmap(':/{}'.format(icon)))
        self.unlockedIcon = QIcon(QPixmap(':/{}'.format(icon2)))
        self.setText('Pick')
        self.setFixedWidth(64)
        # self.setCheckable(True)
        # self.setIconType()
        self.clicked.connect(self.toggle)

    def setIconType(self):
        self.setIcon(self.lockedIcon if self.isChecked() else self.unlockedIcon)

    def toggle(self):
        self.setIconType()
        self.pressedSignal.emit(self.isChecked())


class pickObjectWidget(QWidget):
    setActiveObjectSignal = Signal()
    modeChangedSignal = Signal(bool)
    lockChangedSignal = Signal(bool)

    def __init__(self, *args, **kwargs):
        super(pickObjectWidget, self).__init__(parent=wrapInstance(int(omUI.MQtUtil.mainWindow()), QWidget))
        self.mainLayout = QHBoxLayout()
        self.infoLayout = QHBoxLayout()

        self.mainLayout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self.mainLayout)
        self.pickBtn = QPushButton('Pick Current')

        self.ObjLabel = QLabel('Object ::')
        self.ObjLabel.setFixedWidth(btnWidth)
        self.currentObjLabel = QLabel('None')
        self.mainLayout.addLayout(self.infoLayout)
        self.infoLayout.addWidget(self.ObjLabel)
        self.infoLayout.addWidget(self.currentObjLabel)
        # self.mainLayout.addWidget(self.centre)
        self.mainLayout.addWidget(self.pickBtn)
        # self.mainLayout.addWidget(self.modeBtn)

        self.pickBtn.clicked.connect(self.pickButtonPress)

    @Slot()
    def pickButtonPress(self):
        self.setActiveObjectSignal.emit()

    @Slot()
    def sendModeChangedSignal(self):
        # self.modeChangedSignal.emit(self.modeBtn.isChecked())
        self.modeChangedSignal.emit(True)
        self.changeState()


class pickDirectionWidget(QFrame):
    setActiveObjectSignal = Signal()  # in case the main ui needs to keep track?
    upDownSignal = Signal()  # in case the main ui needs to keep track?
    leftRightSignal = Signal()  # in case the main ui needs to keep track?
    downMultiSignal = Signal()  # in case the main ui needs to keep track?
    upMultiSignal = Signal()  # in case the main ui needs to keep track?
    setLockStateSignal = Signal(bool)
    directionPressedObjectSignal = Signal(str)  # in case the main ui needs to keep track?
    applyButtonPressedSignal = Signal(str, str, str, str, str)
    loopChanged = Signal(bool)
    reciprocateChanged = Signal(bool)
    endOnSelfChanged = Signal(bool)
    activeObject = None

    def __init__(self, mainWindow, *args, **kwargs):
        QFrame.__init__(self, *args, **kwargs)
        self.mainWindow = mainWindow
        self.mode = False
        self.lockState = False
        # self.setFrameStyle(QFrame.Panel | QFrame.Raised)\

        self.setStyleSheet("QFrame {"
                           "border-width: 2;"
                           "border-radius: 4;"
                           "border-style: solid;"
                           "border-color: #222222}"
                           )

        # self.setTitle("Pickwalk")
        self.setMaximumWidth(420)
        self.mainLayout = QVBoxLayout()

        self.mainLayout.setSpacing(4)
        self.setContentsMargins(2, 2, 2, 2)
        self.mainLayout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self.mainLayout)
        self.title = QLabel('Basic Pickwalk Setup')
        self.title.setStyleSheet("QLabel {"
                                 "border-width: 0;"
                                 "border-radius: 4;"
                                 "border-style: solid;"
                                 "border-color: #222222;"
                                 "font-weight: bold; font-size: 12px;}"
                                 )
        self.subtitle = QLabel('Quick Add Multiple Pickwalks')
        self.subtitle.setStyleSheet("QLabel {"
                                    "border-width: 0;"
                                    "border-radius: 4;"
                                    "border-style: solid;"
                                    "border-color: #222222;"
                                    "font-weight: bold; font-size: 12px;}"
                                    )
        self.mainLayout.addWidget(self.title)

        self.objectWidget = pickObjectWidget(self.mainWindow)
        self.objectWidget.setStyleSheet(getStylesheet)
        self.objectWidget.setStyleSheet("QFrame {"
                                        "border-width: 0;"
                                        "border-radius: 0;"
                                        "border-style: solid;"
                                        "border-color: #222222}"
                                        )
        self.objectWidget.setActiveObjectSignal.connect(self.setActiveObject)
        self.objectWidget.modeChangedSignal.connect(self.modeChanged)
        self.objectWidget.lockChangedSignal.connect(self.lockChanged)

        '''
        syncOn.png

        '''
        self.quickLeftRight = ChainPickButton(self.mainWindow, label='Quick Left/Right', direction='Left/Right',
                                              icon='syncOn.png',
                                              fixedWidth=True,
                                              width=150,
                                              rotation=0, loop=True)

        self.quickLeftRight.setToolTip(ToolTip_QuickLeftRight)
        self.quickUpDown = ChainPickButton(self.mainWindow, label='Quick Down/Up', direction='Left/Right',
                                           icon='syncOn.png',
                                           fixedWidth=True,
                                           width=150,
                                           rotation=90, loop=False)
        self.quickUpDown.setToolTip(ToolTip_DownUp)
        self.quickDownMulti = ChainPickButton(self.mainWindow, label='Quick Down To Many', direction='DownMult',
                                              icon='camera.png',
                                              fixedWidth=True,
                                              noOption=True,
                                              width=150,
                                              rotation=180, loop=False)
        self.quickDownMulti.setToolTip(ToolTip_DownMulti)
        self.quickUpMulti = ChainPickButton(self.mainWindow, label='Quick Up From Many', direction='Left/Right',
                                            icon='camera.png',
                                            fixedWidth=True,
                                            noOption=True,
                                            width=150,
                                            rotation=180, loop=False)
        self.quickUpMulti.setToolTip(ToolTip_UpMulti)
        self.upBtn = DirectionPickButton(self.mainWindow, label='Up', direction='up', icon='timeend.png', rotation=90)
        self.downBtn = DirectionPickButton(self.mainWindow, label='Down', direction='down', icon='timeend.png',
                                           rotation=270)
        self.leftBtn = DirectionPickButton(self.mainWindow, label='Left', direction='left', icon='timeend.png',
                                           rotation=0)
        self.rightBtn = DirectionPickButton(self.mainWindow, label='Right', direction='right', icon='timeend.png',
                                            rotation=180)

        self.applyButton = QPushButton('Apply')
        self.applyButton.clicked.connect(self.applyData)

        self.quickLeftRight.pressedSignal.connect(self.inputSignal_quickLeftRight)
        self.quickUpDown.pressedSignal.connect(self.inputSignal_quickUpDown)
        self.quickDownMulti.pressedSignal.connect(self.inputSignal_quickDownMulti)
        self.quickUpMulti.pressedSignal.connect(self.inputSignal_quickUpMulti)

        self.mainLayout.addWidget(self.objectWidget)
        # self.dirHLayout.addWidget(self.chainOptionWidget)
        self.mainLayout.addWidget(self.upBtn)
        self.mainLayout.addWidget(self.downBtn)
        self.mainLayout.addWidget(self.leftBtn)
        self.mainLayout.addWidget(self.rightBtn)
        self.mainLayout.addWidget(self.applyButton)
        self.mainLayout.addWidget(self.subtitle)

        self.mainLayout.addWidget(self.quickLeftRight)
        self.mainLayout.addWidget(self.quickUpDown)
        self.mainLayout.addWidget(self.quickDownMulti)
        self.mainLayout.addWidget(self.quickUpMulti)

        self.allButtons = [
            self.upBtn,
            self.downBtn,
            self.leftBtn,
            self.rightBtn,
            # self.upSkipBtn,
            # self.downSkipBtn,
            # self.leftSkipBtn,
            # self.rightSkipBtn,
        ]
        '''
        for btn in self.allButtons:
            btn.pressedSignal.connect(self.inputSignal_pickDirection)
        '''

    def applyData(self):
        self.mainWindow.currentDestination = self.objectWidget.currentObjLabel.text()
        self.mainWindow.currentTargetUp = self.upBtn.lineEdit.text()
        self.mainWindow.currentTargetDown = self.downBtn.lineEdit.text()
        self.mainWindow.currentTargetLeft = self.leftBtn.lineEdit.text()
        self.mainWindow.currentTargetRight = self.rightBtn.lineEdit.text()
        self.applyButtonPressedSignal.emit(self.objectWidget.currentObjLabel.text(),
                                           self.upBtn.lineEdit.text(),
                                           self.downBtn.lineEdit.text(),
                                           self.leftBtn.lineEdit.text(),
                                           self.rightBtn.lineEdit.text()
                                           )

    def displayCurrentData(self, data, activeObject):
        if not activeObject:
            self.clear()
            return
        self.objectWidget.currentObjLabel.setText(activeObject)
        walkData = data.objectDict.get(activeObject, str())
        if walkData:
            if walkData.up:
                self.setWidgetText(self.upBtn.lineEdit, walkData.up)
            if walkData.down:
                self.setWidgetText(self.downBtn.lineEdit, walkData.down)
            if walkData.left:
                self.setWidgetText(self.leftBtn.lineEdit, walkData.left)
            if walkData.right:
                self.setWidgetText(self.rightBtn.lineEdit, walkData.right)
        else:
            self.clear(obj=False)

    def setWidgetText(self, widget, value):
        if isinstance(value, tuple):
            value = str()
        '''
        if str(value).lower() == 'none':
            value = str()
        '''
        widget.setText(value)

    def clear(self, obj=True):
        if obj: self.objectWidget.currentObjLabel.setText('None')
        self.upBtn.lineEdit.setText('')
        self.downBtn.lineEdit.setText('')
        self.leftBtn.lineEdit.setText('')
        self.rightBtn.lineEdit.setText('')

    @Slot()
    def lockChanged(self, data):
        self.lockState = data
        self.setLockStateSignal.emit(data)

    @Slot()
    def modeChanged(self, data):
        self.mode = data

    @Slot()
    def setActiveObject(self):
        self.setActiveObjectSignal.emit()

    @Slot()
    def inputSignal_pickDirection(self, direction):
        direction = '{0}{1}'.format(direction, {True: 'Skip', False: ''}[self.mode])
        self.directionPressedObjectSignal.emit(direction)

    @Slot()
    def inputSignal_quickLeftRight(self, *args):
        self.leftRightSignal.emit()

    @Slot()
    def inputSignal_quickUpDown(self, *args):
        self.upDownSignal.emit()

    @Slot()
    def inputSignal_quickDownMulti(self, *args):
        self.downMultiSignal.emit()

    @Slot()
    def inputSignal_quickUpMulti(self, *args):
        self.upMultiSignal.emit()

    @Slot()
    def sendloopChangedSignal(self, data):
        self.loopChanged.emit(data)

    @Slot()
    def sendreciprocateChangedSignal(self, data):
        self.reciprocateChanged.emit(data)

    @Slot()
    def sendEndOnSelfChangedSignal(self, data):
        self.endOnSelfChanged.emit(data)


class pickContextDirectionWidget(QFrame):
    setActiveObjectSignal = Signal()  # in case the main ui needs to keep track?
    upDownSignal = Signal()  # in case the main ui needs to keep track?
    leftRightSignal = Signal()  # in case the main ui needs to keep track?
    setLockStateSignal = Signal(bool)
    directionPressedObjectSignal = Signal(str, str, str)  # in case the main ui needs to keep track?

    activeObject = None

    def __init__(self, *args, **kwargs):
        QFrame.__init__(self, *args, **kwargs)
        self.mode = False
        self.lockState = False
        self.activeObject = ''
        self.activeDestination = ''
        # self.setFrameStyle(QFrame.Panel | QFrame.Raised)\

        self.setStyleSheet("QFrame {"
                           "border-width: 2;"
                           "border-radius: 4;"
                           "border-style: solid;"
                           "border-color: #222222}"
                           )

        # self.setTitle("Pickwalk")
        self.setMaximumWidth(420)
        self.mainLayout = QVBoxLayout()
        self.midLayout = QHBoxLayout()
        self.dirHLayout = QHBoxLayout()
        self.dirMidLayout = QVBoxLayout()

        self.leftLayout = QVBoxLayout()
        self.gridLayout = QGridLayout()
        self.gridLayout.setSpacing(4)
        self.mainLayout.setSpacing(4)

        self.mainLayout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self.mainLayout)
        self.title = QLabel('Context Pickwalk Assignment')
        self.title.setStyleSheet("QLabel {"
                                 "border-width: 0;"
                                 "border-radius: 4;"
                                 "border-style: solid;"
                                 "border-color: #222222;"
                                 "font-weight: bold; font-size: 12px;}"
                                 )
        self.mainLayout.addWidget(self.title)

        self.upBtn = standardPickButton(label='', direction='up', fixedWidth=True, icon='timeend.png', rotation=90)
        self.downBtn = standardPickButton(label='', direction='down', fixedWidth=True, icon='timeend.png', rotation=270)
        self.leftBtn = standardPickButton(label='', direction='left', fixedWidth=True, icon='timeend.png', rotation=0)
        self.rightBtn = standardPickButton(label='', direction='right', fixedWidth=True, icon='timeend.png',
                                           rotation=180)

        self.ObjLabel = QLabel('Object ::')
        self.ObjLabel.setFixedWidth(btnWidth)
        self.currentObjLabel = QLabel('None')

        self.destLabel = QLabel('Destination ::')
        self.destLabel.setFixedWidth(btnWidth)
        self.currentDestLabel = QLabel('None')
        self.objLayout = QHBoxLayout()
        self.destLayout = QHBoxLayout()

        self.stylesheetFix(self.ObjLabel)
        self.stylesheetFix(self.currentObjLabel)
        self.stylesheetFix(self.destLabel)
        self.stylesheetFix(self.currentDestLabel)

        self.mainLayout.addLayout(self.objLayout)
        self.mainLayout.addLayout(self.destLayout)
        self.objLayout.addWidget(self.ObjLabel)
        self.objLayout.addWidget(self.currentObjLabel)
        self.destLayout.addWidget(self.destLabel)
        self.destLayout.addWidget(self.currentDestLabel)
        self.mainLayout.addLayout(self.leftLayout)
        self.leftLayout.addLayout(self.dirHLayout)

        self.dirHLayout.addWidget(self.leftBtn)
        self.dirMidLayout.addWidget(self.upBtn)
        self.dirMidLayout.addWidget(self.downBtn)
        self.dirHLayout.addLayout(self.dirMidLayout)
        self.dirHLayout.addWidget(self.rightBtn)

        self.allButtons = [
            self.upBtn,
            self.downBtn,
            self.leftBtn,
            self.rightBtn,
            # self.upSkipBtn,
            # self.downSkipBtn,
            # self.leftSkipBtn,
            # self.rightSkipBtn,
        ]
        for btn in self.allButtons:
            btn.pressedSignal.connect(self.inputSignal_pickDirection)
            btn.setFixedWidth(32)

    def stylesheetFix(self, widget):
        widget.setStyleSheet("QLabel {"
                             "border-width: 0;"
                             "border-radius: 4;"
                             "border-style: solid;"
                             "border-color: #222222}"
                             )

    @Slot()
    def lockChanged(self, data):
        self.lockState = data
        self.setLockStateSignal.emit(data)

    @Slot()
    def modeChanged(self, data):
        self.mode = data

    def setActiveObject(self):
        sel = pm.ls(selection=True, type='transform')
        if not sel:
            # pm.warning('No objects selected')
            self.currentObjLabel.setText("None")
            return
        if len(sel) > 1:
            return
        else:
            lbl = sel[0].stripNamespace()
            self.activeObject = lbl
            self.currentObjLabel.setText(lbl)

    def setActiveDestination(self, data):
        self.activeDestination = data
        self.currentDestLabel.setText(data)

    @Slot()
    def inputSignal_pickDirection(self, direction):
        direction = '{0}{1}'.format(direction, {True: 'Skip', False: ''}[self.mode])
        if not self.activeObject:
            return pm.warning('No current object')
        if not self.activeDestination:
            return pm.warning('No current object')
        self.directionPressedObjectSignal.emit(direction, self.activeObject, self.activeDestination)

    @Slot()
    def inputSignal_quickLeftRight(self):
        self.leftRightSignal.emit()

    @Slot()
    def inputSignal_quickUpDown(self):
        self.upDownSignal.emit()

    @Slot()
    def sendloopChangedSignal(self, data):
        self.loopChanged.emit(data)

    @Slot()
    def sendreciprocateChangedSignal(self, data):
        self.reciprocateChanged.emit(data)

    @Slot()
    def sendEndOnSelfChangedSignal(self, data):
        self.endOnSelfChanged.emit(data)


class LoopCBWidget(QFrame):
    loopChanged = Signal(bool)

    def __init__(self, loop=False, label=str, *args, **kwargs):
        QFrame.__init__(self, *args, **kwargs)
        self.mainLayout = QVBoxLayout()
        self.mainLayout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self.mainLayout)
        self.checkbox = QCheckBox(label)
        self.checkbox.setChecked(loop)
        self.mainLayout.addWidget(self.checkbox)

        self.checkbox.clicked.connect(self.sendloopChangedSignal)
        self.setStyleSheet("QFrame {"
                           "border-width: 0;"
                           "border-radius: 0;"
                           "border-style: solid;"
                           "border-color: #222222}"
                           )

    @Slot()
    def sendloopChangedSignal(self):
        self.loopChanged.emit(self.checkbox.isChecked())


class pickChainWidget(QFrame):
    loopChanged = Signal(bool)
    reciprocateChanged = Signal(bool)
    endOnSelfChanged = Signal(bool)

    def __init__(self, *args, **kwargs):
        QFrame.__init__(self, *args, **kwargs)
        self.mainLayout = QVBoxLayout()
        self.mainLayout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self.mainLayout)
        self.loop = QCheckBox('loop')
        self.reciprocate = QCheckBox('reciprocate')
        self.endOnSelf = QCheckBox('end on self')
        # self.reciprocate.setChecked(True)
        self.reciprocate.setChecked(True)

        self.mainLayout.addWidget(self.loop)
        self.mainLayout.addWidget(self.reciprocate)
        self.mainLayout.addWidget(self.endOnSelf)

        self.loop.clicked.connect(self.sendloopChangedSignal)
        self.reciprocate.clicked.connect(self.sendreciprocateChangedSignal)
        self.endOnSelf.clicked.connect(self.sendendOnSelfChangedSignal)

        self.sendreciprocateChangedSignal()
        self.setStyleSheet("QFrame {"
                           "border-width: 0;"
                           "border-radius: 0;"
                           "border-style: solid;"
                           "border-color: #222222}"
                           )

    @Slot()
    def sendloopChangedSignal(self):
        self.loopChanged.emit(self.loop.isChecked())

    @Slot()
    def sendreciprocateChangedSignal(self):
        self.reciprocateChanged.emit(self.reciprocate.isChecked())

    @Slot()
    def sendendOnSelfChangedSignal(self):
        self.endOnSelfChanged.emit(self.endOnSelf.isChecked())


class labelledLineEdit(QWidget):
    label = None
    lineEdit = None
    editedSignal = Signal(str)

    def __init__(self, text=str, hasButton=False, buttonLabel=str, obj=False):
        super(labelledLineEdit, self).__init__()
        self.obj = obj

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self.layout)
        self.label = QLabel(text)
        self.lineEdit = QLineEdit()
        self.lineEdit.textChanged.connect(self.sendtextChangedSignal)
        self.button = standardPickButton(label=buttonLabel, direction='left', icon='timeend.png', rotation=0)
        self.button.setFixedWidth(80)
        if self.obj:
            self.button.clicked.connect(self.pickObject)
        else:
            self.button.clicked.connect(self.pickChannel)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.lineEdit)
        if hasButton:
            self.layout.addWidget(self.button)
        self.label.setFixedWidth(60)
        # elf.lineEdit.setFixedWidth(200)
        self.label.setStyleSheet("QFrame {"
                                 "border-width: 0;"
                                 "border-radius: 0;"
                                 "border-style: solid;"
                                 "border-color: #222222}"
                                 )

    @Slot()
    def sendtextChangedSignal(self):
        self.editedSignal.emit(self.lineEdit.text())

    def pickChannel(self, *args):
        channels = mel.eval('selectedChannelBoxPlugs')
        if not channels:
            pm.warning('no channel selected')
        self.lineEdit.setText(channels[0].split(':')[-1])

    def pickObject(self, *args):
        sel = cmds.ls(sl=True)
        if not sel:
            pm.warning('no object selected')
        self.lineEdit.setText(sel[0].split(':')[-1] + '_in')


class LineEdit(QWidget):
    label = None
    lineEdit = None
    editedSignal = Signal(str)

    def __init__(self, text=str, tooltip=str(), placeholderTest=str()):
        super(LineEdit, self).__init__()

        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self.layout)
        self.label = QLabel(text)
        self.lineEdit = QLineEdit()
        self.cle_action_pick = self.lineEdit.addAction(QIcon(":/targetTransfoPlus.png"), QLineEdit.TrailingPosition)
        self.cle_action_pick.setToolTip(tooltip)
        self.lineEdit.setPlaceholderText(placeholderTest)
        self.lineEdit.textChanged.connect(self.sendtextChangedSignal)

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.lineEdit)
        self.label.setFixedWidth(60)

        self.label.setStyleSheet("QFrame {"
                                 "border-width: 0;"
                                 "border-radius: 0;"
                                 "border-style: solid;"
                                 "border-color: #222222}"
                                 )

    @Slot()
    def sendtextChangedSignal(self):
        self.editedSignal.emit(self.lineEdit.text())


class labelledDoubleSpinBox(QWidget):
    editedSignal = Signal(float)

    def __init__(self, text=str, helpLine=None, labelWidth=60):
        super(labelledDoubleSpinBox, self).__init__()
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self.layout)
        self.label = QLabel(text)
        self.spinBox = QDoubleSpinBox()
        # self.label.setFixedWidth(60)
        # self.spinBox.setFixedWidth(200)
        self.spinBox.setValue(0.5)
        self.spinBox.setSingleStep(0.1)
        self.spinBox.valueChanged.connect(self.sendValueChangedSignal)

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.spinBox)

        self.label.setFixedWidth(labelWidth)
        self.label.setStyleSheet("QFrame {"
                                 "border-width: 0;"
                                 "border-radius: 0;"
                                 "border-style: solid;"
                                 "border-color: #222222}"
                                 )
        if helpLine:
            self.help = QLabel(helpLine)
            self.layout.addWidget(self.help)
            self.help.setStyleSheet("QFrame {"
                                    "border-width: 0;"
                                    "border-radius: 0;"
                                    "border-style: solid;"
                                    "border-color: #222222}"
                                    )
            self.layout.addStretch()

    @Slot()
    def sendValueChangedSignal(self):
        self.editedSignal.emit(self.spinBox.value())


class ControlListWidget(QWidget):
    pressedSignal = Signal(list())
    newDestinationSignal = Signal(str, str, list)
    newConditionDestinationSignal = Signal(QStandardItem)
    getFromRigSignal = Signal()

    def __init__(self, CLS=None, label='BLANK'):
        super(ControlListWidget, self).__init__()
        self.CLS = CLS
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setMinimumWidth(120)
        self.width = 300
        self.setLayout(self.layout)
        self.topLayout = QVBoxLayout()
        self.layout.addLayout(self.topLayout)
        self.label = QLabel(label)
        self.horizontalLayout = QVBoxLayout()

        self.filterLineEdit = QLineEdit()
        self.filterLineEdit.setClearButtonEnabled(True)
        self.filterLineEdit.addAction(QIcon(":/resources/search.ico"), QLineEdit.LeadingPosition)
        self.filterLineEdit.setPlaceholderText("Search...")
        self.categoryLabel = QLabel('Category ::')
        self.addCategoryBtn = QPushButton('+')
        self.removeCategoryBtn = QPushButton('-')

        self.categoryOption = QComboBox()
        self.categoryOption.setMinimumWidth(120)
        self.addCategoryBtn.clicked.connect(self.categoryAdded)
        self.removeCategoryBtn.clicked.connect(self.categoryRemoved)
        # self.label.setFixedWidth(60)
        # self.spinBox.setFixedWidth(200)
        # self.spinBox.setValue(0.5)
        # self.spinBox.setSingleStep(0.1)

        # self.spinBox.valueChanged.connect(self.sendValueChangedSignal)
        self.getFromRigButton = QPushButton('Get from object attributes')
        self.getFromRigButton.clicked.connect(self.getFromRig)
        self.topLayout.addWidget(self.label)
        self.topLayout.addLayout(self.horizontalLayout)
        self.topLayout.addWidget(self.filterLineEdit)
        self.horizontalLayout.addWidget(self.filterLineEdit)

        # self.topLayout.addWidget(self.categoryLabel)
        # self.topLayout.addWidget(self.categoryOption)
        # self.topLayout.addWidget(self.addCategoryBtn)
        # self.topLayout.addWidget(self.removeCategoryBtn)
        # self.layout.addWidget(self.spinBox)
        # self.layout.addStretch()
        '''
        self.label.setStyleSheet("QFrame {"
                                 "border-width: 0;"
                                 "border-radius: 0;"
                                 "border-style: solid;"
                                 "border-color: #222222}"
                                 )
        '''
        self.treeView = QTreeView()
        self.treeView.setAlternatingRowColors(True)
        self.treeView.setStyleSheet("QTreeView {"
                                    "alternate-background-color: #464848 ;"
                                    "background: #323232;}"
                                    )
        self.proxyModel = QSortFilterProxyModel()
        self.proxyModel.setDynamicSortFilter(True)
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Control', 'up', 'down', 'left', 'right'])
        self.proxyModel.setSourceModel(self.model)
        self.treeView.setModel(self.proxyModel)
        self.treeView.clicked.connect(self.itemClicked)
        self.filterLineEdit.textChanged.connect(self.filterRegExpChanged)
        self.treeView.setSizeAdjustPolicy(QListWidget.AdjustToContents)
        self.treeView.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.header = self.treeView.header()
        self.header.setStretchLastSection(False)
        self.header.setSectionResizeMode(QHeaderView.ResizeToContents)
        # self.header.setSectionResizeMode(4, QHeaderView.Stretch)

        # self.header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.treeView.setSizeAdjustPolicy(QListWidget.AdjustToContents)

        # spacerItem = QSpacerItem(20, 80, QSizePolicy.Minimum, QSizePolicy.Expanding)
        # self.layout.addItem(spacerItem)

        self.toolTypeScrollArea = QScrollArea()
        self.toolTypeScrollArea.setWidget(self.treeView)
        self.toolTypeScrollArea.setWidgetResizable(True)
        self.layout.addWidget(self.toolTypeScrollArea)
        self.layout.addWidget(self.getFromRigButton)
        # self.layout.addStretch(1)
        # self.toolTypeScrollArea.setFixedWidth(148)
        self.updateCategoryList()
        self.updateView()

    def filterRegExpChanged(self, value):
        regExp = QRegExp(value)
        self.proxyModel.setFilterRegExp(regExp)

    def updateCategoryList(self):
        self.categoryOption.clear()
        self.categoryOption.addItem('None')
        for c in self.CLS.walkData.categoryKeys.keys():
            self.categoryOption.addItem(c)
        self.categoryOption.currentIndexChanged.connect(self.categoryChanged)

    def categoryChanged(self, i):
        pass

    def categoryAdded(self):
        prompt = promptWidget(title='Add new category', text='Name ::', defaultInput='New', buttonText='OK')
        prompt.saveSignal.connect(self.inputSignal)

    def inputSignal(self, input):
        if input not in self.CLS.walkData.categoryKeys.keys():
            self.CLS.walkData.categoryKeys[input] = list()
            self.updateCategoryList()

    def categoryRemoved(self):
        self.categoryOption.removeItem(self.categoryOption.currentIndex())

    def updateView(self):
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Control', 'up', 'down', 'left', 'right'])
        # self.listwidget.addItems(self.CLS.walkData.objectDict.keys())
        for item in sorted(self.CLS.walkData.objectDict.keys()):
            data = self.CLS.walkData.objectDict[item]
            controlItem = QStandardItem(item)
            controlItem.setToolTip(ToolTip_ctrlClickSelect)
            upItem = QStandardItem(str(data.up))
            downItem = QStandardItem(str(data.down))
            leftItem = QStandardItem(str(data.left))
            rightItem = QStandardItem(str(data.right))
            upItem.setToolTip(ToolTip_destinationPicker)
            downItem.setToolTip(ToolTip_destinationPicker)
            leftItem.setToolTip(ToolTip_destinationPicker)
            rightItem.setToolTip(ToolTip_destinationPicker)

            controlItem.control = item
            upItem.direction = 'up'
            upItem.control = item
            downItem.direction = 'down'
            downItem.control = item
            leftItem.direction = 'left'
            leftItem.control = item
            rightItem.direction = 'right'
            rightItem.control = item

            self.model.appendRow([controlItem, upItem, downItem, leftItem, rightItem])

    def getFromRig(self):
        self.getFromRigSignal.emit()

    @Slot()
    def sendValueChangedSignal(self):
        self.pressedSignal.emit(list())

    def itemClicked(self, index):
        modifiers = QApplication.keyboardModifiers()
        item = self.model.itemFromIndex(self.proxyModel.mapToSource(index))

        if not hasattr(item, 'control'):
            return

        if modifiers == Qt.ShiftModifier:
            self.sendNewConditionDestinationSignal(item)

        elif modifiers == Qt.ControlModifier:
            if hasattr(item, 'direction'):
                sel = cmds.ls(sl=True, type='transform')
                if not sel:
                    return pm.warning('nothing selected')
                walkObject = sel[0].split(':')[-1] + '_in'
                item.setText(walkObject)
                self.sendNewDestinationSignal(item.control, item.direction, sel)
            else:
                cmds.select(item.control, replace=True)

    @Slot()
    def sendNewConditionDestinationSignal(self, item):
        self.newConditionDestinationSignal.emit(item)

    @Slot()
    def sendNewDestinationSignal(self, control, direction, item):
        self.newDestinationSignal.emit(control, direction, item)


class QTreeSingleViewWidget(QFrame):
    pressedSignal = Signal(str)

    def __init__(self, CLS=None, label='BLANK'):
        super(QTreeSingleViewWidget, self).__init__()
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        # self.setMinimumWidth(120)
        # self.setMaximumWidth(200)
        # self.width = 300
        self.setLayout(self.layout)
        self.topLayout = QVBoxLayout()
        self.layout.addLayout(self.topLayout)
        self.label = QLabel(label)
        self.filterLineEdit = QLineEdit()
        self.filterLineEdit.setClearButtonEnabled(True)
        self.filterLineEdit.addAction(QIcon(":/resources/search.ico"), QLineEdit.LeadingPosition)
        self.filterLineEdit.setPlaceholderText("Search...")
        # self.categoryLabel = QLabel('Category ::')
        # self.addCategoryBtn = QPushButton('+')
        # self.removeCategoryBtn = QPushButton('-')

        # self.categoryOption = QComboBox()
        # self.categoryOption.setMinimumWidth(120)
        # self.addCategoryBtn.clicked.connect(self.categoryAdded)
        # self.removeCategoryBtn.clicked.connect(self.categoryRemoved)
        # self.label.setFixedWidth(60)
        # self.spinBox.setFixedWidth(200)
        # self.spinBox.setValue(0.5)
        # self.spinBox.setSingleStep(0.1)

        # self.spinBox.valueChanged.connect(self.sendValueChangedSignal)

        self.topLayout.addWidget(self.label)
        self.topLayout.addWidget(self.filterLineEdit)
        # self.topLayout.addWidget(self.categoryLabel)
        # self.topLayout.addWidget(self.categoryOption)
        # self.topLayout.addWidget(self.addCategoryBtn)
        # self.topLayout.addWidget(self.removeCategoryBtn)
        # self.layout.addWidget(self.spinBox)
        # self.layout.addStretch()
        '''
        self.label.setStyleSheet("QFrame {"
                                 "border-width: 0;"
                                 "border-radius: 0;"
                                 "border-style: solid;"
                                 "border-color: #222222}"
                                 )
        '''
        self.listView = QListView()

        self.proxyModel = QSortFilterProxyModel()
        self.proxyModel.setDynamicSortFilter(True)
        self.model = QStandardItemModel()
        # self.model.setHorizontalHeaderLabels(['Destination'])
        self.proxyModel.setSourceModel(self.model)
        self.listView.setModel(self.proxyModel)
        self.listView.clicked.connect(self.itemClicked)
        self.model.itemChanged.connect(self.itemChanged)
        self.filterLineEdit.textChanged.connect(self.filterRegExpChanged)
        # self.treeView.setSizeAdjustPolicy(QListWidget.AdjustToContents)
        self.listView.setSelectionBehavior(QAbstractItemView.SelectItems)

        # self.header.setSectionResizeMode(QHeaderView.ResizeToContents)

        # self.header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.listView.setSizeAdjustPolicy(QListWidget.AdjustToContents)

        # spacerItem = QSpacerItem(20, 80, QSizePolicy.Minimum, QSizePolicy.Expanding)
        # self.layout.addItem(spacerItem)

        self.toolTypeScrollArea = QScrollArea()
        self.toolTypeScrollArea.setWidget(self.listView)
        self.toolTypeScrollArea.setWidgetResizable(True)
        self.layout.addWidget(self.toolTypeScrollArea)
        # self.layout.addStretch(1)
        # self.toolTypeScrollArea.setFixedWidth(148)
        # self.updateCategoryList()
        # self.updateView()

    @Slot()
    def sendValueChangedSignal(self):
        self.pressedSignal.emit(list())

    def appendItem(self, i):
        item = QStandardItem(i)
        self.model.appendRow(item)

    def removeItem(self, item):
        for item in self.model.findItems(item):
            self.model.removeRow(item.row())

    def updateView(self, items):
        self.model.clear()
        self.listView.blockSignals(True)
        for i in items:
            self.appendItem(i)
        self.listView.blockSignals(False)

    def filterRegExpChanged(self, value):
        regExp = QRegExp(value)
        self.proxyModel.setFilterRegExp(regExp)

    def itemClicked(self, index):
        modifiers = QApplication.keyboardModifiers()
        item = self.model.itemFromIndex(self.proxyModel.mapToSource(index))
        self.pressedSignal.emit(item.text())

    def itemChanged(self, item):
        pass


class DestinationListWidget(QFrame):
    pressedSignal = Signal(str)
    selectedSignal = Signal(str)
    applySignal = Signal(str)

    def __init__(self, CLS=None, label='BLANK'):
        super(DestinationListWidget, self).__init__()
        self.CLS = CLS
        self.mainLayout = QVBoxLayout()
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.setMinimumWidth(120)
        self.setMaximumWidth(200)
        # self.width = 300
        self.setLayout(self.mainLayout)
        self.topLayout = QVBoxLayout()
        self.mainLayout.addLayout(self.topLayout)
        self.label = QLabel(label)
        self.applyButton = QPushButton('Replace selection')
        self.applyButton.clicked.connect(self.applyToSelected)
        self.filterLineEdit = QLineEdit()
        self.filterLineEdit.setClearButtonEnabled(True)
        self.filterLineEdit.addAction(QIcon(":/resources/search.ico"), QLineEdit.LeadingPosition)
        self.filterLineEdit.setPlaceholderText("Search...")
        # self.categoryLabel = QLabel('Category ::')
        # self.addCategoryBtn = QPushButton('+')
        # self.removeCategoryBtn = QPushButton('-')

        # self.categoryOption = QComboBox()
        # self.categoryOption.setMinimumWidth(120)
        # self.addCategoryBtn.clicked.connect(self.categoryAdded)
        # self.removeCategoryBtn.clicked.connect(self.categoryRemoved)
        # self.label.setFixedWidth(60)
        # self.spinBox.setFixedWidth(200)
        # self.spinBox.setValue(0.5)
        # self.spinBox.setSingleStep(0.1)

        # self.spinBox.valueChanged.connect(self.sendValueChangedSignal)

        self.topLayout.addWidget(self.label)
        self.topLayout.addWidget(self.filterLineEdit)

        # self.topLayout.addWidget(self.categoryLabel)
        # self.topLayout.addWidget(self.categoryOption)
        # self.topLayout.addWidget(self.addCategoryBtn)
        # self.topLayout.addWidget(self.removeCategoryBtn)
        # self.layout.addWidget(self.spinBox)
        # self.layout.addStretch()
        '''
        self.label.setStyleSheet("QFrame {"
                                 "border-width: 0;"
                                 "border-radius: 0;"
                                 "border-style: solid;"
                                 "border-color: #222222}"
                                 )
        '''
        self.treeView = QTreeView()
        self.treeView.setAlternatingRowColors(True)
        self.treeView.setStyleSheet("QTreeView {"
                                    "alternate-background-color: #464848 ;"
                                    "background: #323232;}"
                                    )
        self.proxyModel = QSortFilterProxyModel()
        self.proxyModel.setDynamicSortFilter(True)
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(['Destination'])
        self.proxyModel.setSourceModel(self.model)
        self.treeView.setModel(self.proxyModel)
        self.treeView.clicked.connect(self.itemClicked)
        self.model.itemChanged.connect(self.itemChanged)
        self.filterLineEdit.textChanged.connect(self.filterRegExpChanged)
        # self.treeView.setSizeAdjustPolicy(QListWidget.AdjustToContents)
        self.treeView.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.header = self.treeView.header()
        self.header.setStretchLastSection(True)
        # self.header.setSectionResizeMode(QHeaderView.ResizeToContents)

        # self.header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.treeView.setSizeAdjustPolicy(QListWidget.AdjustToContents)

        # spacerItem = QSpacerItem(20, 80, QSizePolicy.Minimum, QSizePolicy.Expanding)
        # self.layout.addItem(spacerItem)

        self.toolTypeScrollArea = QScrollArea()
        self.toolTypeScrollArea.setWidget(self.treeView)
        self.toolTypeScrollArea.setWidgetResizable(True)
        self.mainLayout.addWidget(self.toolTypeScrollArea)
        self.mainLayout.addWidget(self.applyButton)

        # self.layout.addStretch(1)
        # self.toolTypeScrollArea.setFixedWidth(148)
        # self.updateCategoryList()
        # self.updateView()

    @Slot()
    def sendValueChangedSignal(self):
        self.pressedSignal.emit(list())

    def updateView(self):
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Destination'])
        self.treeView.blockSignals(True)
        for item in sorted(self.CLS.walkData.destinations.keys()):
            # data = self.CLS.walkData.objectDict[item]
            destinationItem = QStandardItem(item)
            destinationItem.setToolTip(ToolTip_DestinationCtrlClickSet)

            destinationItem.destination = item

            self.model.appendRow([destinationItem])
        self.treeView.blockSignals(False)

    def filterRegExpChanged(self, value):
        regExp = QRegExp(value)
        self.proxyModel.setFilterRegExp(regExp)

    def itemClicked(self, index):
        modifiers = QApplication.keyboardModifiers()
        item = self.model.itemFromIndex(self.proxyModel.mapToSource(index))
        if modifiers == Qt.ControlModifier:
            self.pressedSignal.emit(item.text())
        else:
            self.selectedSignal.emit(item.text())

    def applyToSelected(self):
        index = self.treeView.selectedIndexes()[0]
        item = self.model.itemFromIndex(self.proxyModel.mapToSource(index))
        self.applySignal.emit(item.text())

    def itemChanged(self, item):
        pass


class tempPickWidget(QWidget):

    def __init__(self, *args, **kwargs):
        QWidget.__init__(self, *args, **kwargs)
        self.layout = QHBoxLayout()
        self.setLayout(self.layout)
        self.lineEdit = QLineEdit()
        self.layout.addWidget(self.lineEdit)
        self.cle_action_pick = self.lineEdit.addAction(QIcon(":/targetTransfoPlus.png"),
                                                       QLineEdit.TrailingPosition)
        self.cle_action_pick.setToolTip('Placeholder')
        self.cle_action_pick.triggered.connect(self.chooseControl)

    def chooseControl(self):
        pass


class DestinationWidget(QWidget):
    updatedSignal = Signal(list)

    def __init__(self, label='BLANK'):
        super(DestinationWidget, self).__init__()
        self.mainListItem = str()
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.label = QLabel(label)
        self.pickButton = QPushButton('Pick')
        self.addDestinationBtn = QPushButton('+')
        self.removeDestinationBtn = QPushButton('-')
        self.addFromDestinationBtn = QPushButton('From Destinations')
        self.spinBox = QDoubleSpinBox()
        # self.label.setFixedWidth(60)
        # self.spinBox.setFixedWidth(200)
        # self.spinBox.setValue(0.5)
        # self.spinBox.setSingleStep(0.1)

        # self.spinBox.valueChanged.connect(self.sendValueChangedSignal)

        self.layout.addWidget(self.label)
        # self.layout.addWidget(self.spinBox)
        self.layout.addStretch()
        self.label.setStyleSheet("QFrame {"
                                 "border-width: 0;"
                                 "border-radius: 0;"
                                 "border-style: solid;"
                                 "border-color: #222222}"
                                 )
        self.listwidget = QListWidget()
        self.layout.addWidget(self.listwidget)

        self.subLayout = QHBoxLayout()
        self.subLayout.addWidget(self.pickButton)
        self.subLayout.addWidget(self.addDestinationBtn)
        self.subLayout.addWidget(self.removeDestinationBtn)
        self.subLayout2 = QHBoxLayout()
        self.subLayout2.addWidget(self.addFromDestinationBtn)

        self.layout.addLayout(self.subLayout)
        self.layout.addLayout(self.subLayout2)
        self.pickButton.clicked.connect(self.pickButtonPressed)
        self.addDestinationBtn.clicked.connect(self.addButtonPressed)
        self.removeDestinationBtn.clicked.connect(self.removeButtonPressed)
        self.addFromDestinationBtn.clicked.connect(self.addFromDestinationPressed)

    def currentItems(self):
        return [self.listwidget.item(x).text() for x in range(self.listwidget.count())]

    def recieveMainDestinationClicked(self, item):
        self.mainListItem = item

    @Slot()
    def sendUpdateSignal(self):
        self.updatedSignal.emit(self.currentItems())

    def pickButtonPressed(self):
        sel = pm.ls(selection=True, type='transform')
        self.listwidget.clear()
        if sel:
            items = [s.stripNamespace() for s in sel]
            self.listwidget.addItems(items)
        self.sendUpdateSignal()

    def addButtonPressed(self):
        sel = pm.ls(selection=True, type='transform')
        if not sel:
            return
        items = [s.stripNamespace() for s in sel]
        currentItems = self.currentItems()
        resultItems = self.currentItems()
        self.listwidget.clear()
        for i in items:
            if i not in currentItems:
                resultItems.append(i)
        self.listwidget.addItems(resultItems)
        self.sendUpdateSignal()

    def addFromDestinationPressed(self):
        currentItems = self.currentItems()
        resultItems = self.currentItems()

        self.listwidget.clear()
        resultItems.append(self.mainListItem)

        self.listwidget.addItems(resultItems)
        self.sendUpdateSignal()

    def removeButtonPressed(self):
        listItems = self.listwidget.selectedItems()
        if not listItems: return
        for item in listItems:
            self.listwidget.takeItem(self.listwidget.row(item))
        self.sendUpdateSignal()

    def refreshUI(self, targets):
        self.listwidget.clear()
        self.listwidget.addItems(targets)


class MiniDestinationWidget(QWidget):
    updatedSignal = Signal(list)

    def __init__(self, label='BLANK'):
        super(MiniDestinationWidget, self).__init__()
        # self.setFixedWidth(140)
        self.setMaximumWidth(160)
        self.setMaximumHeight(150)
        self.mainListItem = str()
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.label = QLabel(label)
        self.pickButton = QPushButton('Pick')
        self.addDestinationBtn = QPushButton('+')
        self.removeDestinationBtn = QPushButton('-')
        self.addFromDestinationBtn = QPushButton('From Existing Condition')
        self.spinBox = QDoubleSpinBox()
        # self.label.setFixedWidth(60)
        # self.spinBox.setFixedWidth(200)
        # self.spinBox.setValue(0.5)
        # self.spinBox.setSingleStep(0.1)

        # self.spinBox.valueChanged.connect(self.sendValueChangedSignal)

        self.layout.addWidget(self.label)
        # self.layout.addWidget(self.spinBox)
        self.layout.addStretch()
        self.label.setStyleSheet("QFrame {"
                                 "border-width: 0;"
                                 "border-radius: 0;"
                                 "border-style: solid;"
                                 "border-color: #222222}"
                                 )
        self.listwidget = QListWidget()
        self.layout.addWidget(self.listwidget)

        self.subLayout = QHBoxLayout()
        self.subLayout.addWidget(self.pickButton)
        # self.subLayout.addWidget(self.addDestinationBtn)
        # self.subLayout.addWidget(self.removeDestinationBtn)
        # self.subLayout.addWidget(self.addFromDestinationBtn)

        self.layout.addLayout(self.subLayout)

        self.pickButton.clicked.connect(self.pickButtonPressed)
        self.addDestinationBtn.clicked.connect(self.addButtonPressed)
        self.removeDestinationBtn.clicked.connect(self.removeButtonPressed)
        self.addFromDestinationBtn.clicked.connect(self.addFromDestinationPressed)

    def currentItems(self):
        return [self.listwidget.item(x).text() for x in range(self.listwidget.count())]

    def recieveMainDestinationClicked(self, item):
        self.mainListItem = item

    @Slot()
    def sendUpdateSignal(self):
        self.updatedSignal.emit(self.currentItems())

    def pickButtonPressed(self, override=None):
        if not override:
            sel = pm.ls(selection=True, type='transform')
        else:
            sel = override
        self.listwidget.clear()
        if sel:
            items = [s.stripNamespace() for s in sel]
            self.listwidget.addItems(items)
        self.sendUpdateSignal()

    def addButtonPressed(self):
        sel = pm.ls(selection=True, type='transform')
        if not sel:
            return
        items = [s.stripNamespace() for s in sel]
        currentItems = self.currentItems()
        resultItems = self.currentItems()
        self.listwidget.clear()
        for i in items:
            if i not in currentItems:
                resultItems.append(i)
        self.listwidget.addItems(resultItems)
        self.sendUpdateSignal()

    def addFromDestinationPressed(self):
        currentItems = self.currentItems()
        resultItems = self.currentItems()

        self.listwidget.clear()
        resultItems.append(self.mainListItem)

        self.listwidget.addItems(resultItems)
        self.sendUpdateSignal()

    def removeButtonPressed(self):
        listItems = self.listwidget.selectedItems()
        if not listItems: return
        for item in listItems:
            self.listwidget.takeItem(self.listwidget.row(item))
        self.sendUpdateSignal()

    def refreshUI(self, targets):
        self.listwidget.clear()
        self.listwidget.addItems(targets)


class contextPickwalkWidget(QFrame):
    destinationAdded = Signal(dict)
    changed = Signal(str)

    def __init__(self, *args, **kwargs):
        QFrame.__init__(self, *args, **kwargs)
        self.setMaximumWidth(420)
        self.setMaximumHeight(320)
        # self.setTitle("Context pickwalks")
        self.mainLayout = QVBoxLayout()
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.setStyleSheet("QFrame {"
                           "border-width: 2;"
                           "border-radius: 4;"
                           "border-style: solid;"
                           "border-color: #222222}"
                           )
        self.mainLayout.setContentsMargins(2, 2, 2, 2)
        self.setLayout(self.mainLayout)
        self.title = QLabel('Context pickwalk Creation')
        self.title.setStyleSheet("QLabel {"
                                 "border-width: 0;"
                                 "border-radius: 4;"
                                 "border-style: solid;"
                                 "border-color: #222222;"
                                 "font-weight: bold; font-size: 12px;}"
                                 )
        self.nameWidget = labelledLineEdit(text='Name', hasButton=True, buttonLabel='From Sel', obj=True)
        self.conditionAttrWidget = labelledLineEdit(text='Attribute', hasButton=True,
                                                    buttonLabel='From CB')
        self.conditionWidget = labelledDoubleSpinBox('Condition')
        self.destinationsWidget = DestinationWidget(label='Destinations')
        self.destinationsWidget.updatedSignal.connect(self.inputSignal_destinationsUpdated)
        self.altDestinationsWidget = DestinationWidget(label='Alt Destinations')
        self.altDestinationsWidget.updatedSignal.connect(self.inputSignal_altDestinationsUpdated)

        self.mainLayout.addWidget(self.title)

        self.mainLayout.addWidget(self.nameWidget)
        self.mainLayout.addWidget(self.conditionAttrWidget)
        self.mainLayout.addWidget(self.conditionWidget)

        self.splitLayout = QHBoxLayout()
        self.mainLayout.addLayout(self.splitLayout)
        self.splitLayout.addWidget(self.destinationsWidget)
        self.splitLayout.addWidget(self.altDestinationsWidget)

        self.newButton = QPushButton('Add/Update Conditional Destination')
        self.newButton.clicked.connect(self.outputSignal_newDestinationCreated)
        self.mainLayout.addWidget(self.newButton)
        # self.nameWidget.editedSignal.connect(self.inputSignal_nameChanged)
        self.conditionAttrWidget.editedSignal.connect(self.inputSignal_attributehanged)
        self.conditionWidget.editedSignal.connect(self.inputSignal_conditionhanged)

    def outputSignal_newDestinationCreated(self):
        outData = dict()
        outData['destination'] = self.destinationsWidget.currentItems()
        outData['destinationAlt'] = self.altDestinationsWidget.currentItems()
        outData['conditionAttribute'] = self.conditionAttrWidget.lineEdit.text()
        outData['conditionValue'] = self.conditionWidget.spinBox.value()
        outData['name'] = self.nameWidget.lineEdit.text()
        self.destinationAdded.emit(outData)

    def populate(self, item, destinationData):
        self.destinationsWidget.refreshUI(destinationData.destination)
        self.altDestinationsWidget.refreshUI(destinationData.destinationAlt)
        self.conditionAttrWidget.lineEdit.setText(destinationData.conditionAttribute)
        self.conditionWidget.spinBox.setValue(destinationData.conditionValue)
        self.nameWidget.lineEdit.setText(item)

    def inputSignal_destinationsUpdated(self, items):
        print('inputSignal_destinationsPicked,', items)

    def inputSignal_altDestinationsUpdated(self, items):
        print('inputSignal_altDestinationsPicked,', items)

    def inputSignal_nameChanged(self, name):
        print('inputSignal_nameChanged,', name)

    def inputSignal_attributehanged(self, attribute):
        print('inputSignal_namgeChanged,', attribute)

    def inputSignal_conditionhanged(self, value):
        print('inputSignal_conditionhanged,', value)


class PickwalkPopup(BaseDialog):
    destinationAdded = Signal(dict)
    changed = Signal(str)

    def __init__(self, control=None, destination=None, *args, **kwargs):
        super(PickwalkPopup, self).__init__(parent=wrapInstance(int(omUI.MQtUtil.mainWindow()), QWidget),
                                            title='Context pickwalk Creation')
        # TODO - move these functions out of the window and into Pickwalk()
        self.control = control
        self.destination = destination
        self.pickwalk = Pickwalk()
        self.pickwalkWindow = pickwalkMainWindow()
        self.pickwalk.loadLibraryForCurrent()
        self.creator = self.pickwalk.pickwalkCreator


        self.setStyleSheet("QFrame {"
                           "border-width: 2;"
                           "border-radius: 4;"
                           "border-style: solid;"
                           "border-color: #222222}"
                           )
        self.mainLayout.setContentsMargins(4, 4, 4, 4)
        self.setLayout(self.mainLayout)

        self.titleText.setStyleSheet("QLabel {"
                                     "border-width: 0;"
                                     "border-radius: 4;"
                                     "border-style: solid;"
                                     "border-color: #222222;"
                                     "font-weight: bold; font-size: 12px;}"
                                     )

        'Condition Name'
        self.controlWidget = LineEdit(text='Control', tooltip='Pick the control to walk from.',
                                      placeholderTest='pick control')
        self.controlWidget.cle_action_pick.triggered.connect(self.pickControl)

        '''
        self.nameWidget = LineEdit(text='Name', tooltip='Pick name from selected object.',
                                   placeholderTest='enter condition name')
        self.nameWidget.cle_action_pick.triggered.connect(self.pickObject)
        '''
        self.conditionAttrWidget = LineEdit(text='Attribute', tooltip='Pick attribute to control pickwalk.',
                                            placeholderTest='enter condition attribute')
        self.conditionAttrWidget.cle_action_pick.triggered.connect(self.pickAttribute)

        self.conditionWidget = labelledDoubleSpinBox(text='Value',
                                                     helpLine='value > this, use alt destination')
        self.destinationsWidget = MiniDestinationWidget(label='Destinations')
        self.destinationsWidget.updatedSignal.connect(self.inputSignal_destinationsUpdated)
        self.altDestinationsWidget = MiniDestinationWidget(label='Alt Destinations')
        self.altDestinationsWidget.updatedSignal.connect(self.inputSignal_altDestinationsUpdated)

        self.mainLayout.addWidget(self.controlWidget)
        # self.mainLayout.addWidget(self.nameWidget)
        self.mainLayout.addWidget(self.conditionAttrWidget)
        self.mainLayout.addWidget(self.conditionWidget)

        self.splitLayout = QHBoxLayout()
        self.mainLayout.addLayout(self.splitLayout)
        self.splitLayout.addWidget(self.destinationsWidget)
        self.splitLayout.addWidget(self.altDestinationsWidget)

        self.upBtn = standardPickButton(label='Up',
                                        direction='up',
                                        icon='timeend.png',
                                        rotation=90,
                                        fixedWidth=False,
                                        width=48)
        self.downBtn = standardPickButton(label='Down',
                                          direction='down',
                                          icon='timeend.png',
                                          rotation=270,
                                          fixedWidth=False,
                                          width=48)
        self.leftBtn = standardPickButton(label='Left',
                                          direction='left',
                                          icon='timeend.png',
                                          rotation=0,
                                          fixedWidth=False,
                                          width=48)
        self.rightBtn = standardPickButton(label='Right',
                                           direction='right',
                                           icon='timeend.png',
                                           rotation=180,
                                           fixedWidth=False,
                                           width=48)

        applyLabel = QLabel('Walk Direction')
        applyLabel.setAlignment(Qt.AlignCenter)
        applyLabel.setStyleSheet("QLabel {"
                                 "border-width: 0;"
                                 "border-radius: 4;"
                                 "border-style: solid;"
                                 "border-color: #222222;"
                                 "font-weight: bold; font-size: 12px;}"
                                 )
        self.mainLayout.addWidget(applyLabel)
        self.directionLayout = QHBoxLayout()
        self.directionLayout.addWidget(self.upBtn)
        self.directionLayout.addWidget(self.downBtn)
        self.directionLayout.addWidget(self.leftBtn)
        self.directionLayout.addWidget(self.rightBtn)
        self.mainLayout.addLayout(self.directionLayout)
        self.conditionWidget.editedSignal.connect(self.inputSignal_conditionhanged)

        self.upBtn.pressedSignal.connect(self.addWalk)
        self.downBtn.pressedSignal.connect(self.addWalk)
        self.leftBtn.pressedSignal.connect(self.addWalk)
        self.rightBtn.pressedSignal.connect(self.addWalk)

        self.setFixedSize(self.sizeHint())
        self.pickControl(self.control)
        if self.destination:
            if not isinstance(self.destination, list):
                self.destination = [self.destination]
            self.destinationsWidget.pickButtonPressed(self.destination)
        self.setStyleSheet(getqss.getStyleSheet())

    def pickControl(self, control=None, *args):
        sel = cmds.ls(sl=True)
        if not sel:
            return pm.warning('no object selected')
        controlString = sel[0].split(':')[-1]
        if len(sel) > 1:
            controlString += '...'
        self.controlWidget.lineEdit.setText(controlString)
        self.controls = [s.split(':')[-1] for s in sel]

    def pickObject(self, *args):
        sel = cmds.ls(sl=True)
        if not sel:
            pm.warning('no object selected')
        self.nameWidget.lineEdit.setText(sel[0].split(':')[-1] + '_in')

    def pickAttribute(self, *args):
        channels = mel.eval('selectedChannelBoxPlugs')
        if not channels:
            return pm.warning('no channel selected')
        self.conditionAttrWidget.lineEdit.setText(channels[0].split(':')[-1])

    def outputSignal_newDestinationCreated(self):
        pass

    def populate(self, item, destinationData):
        self.destinationsWidget.refreshUI(destinationData.destination)
        self.altDestinationsWidget.refreshUI(destinationData.destinationAlt)
        self.conditionAttrWidget.lineEdit.setText(destinationData.conditionAttribute)
        self.conditionWidget.spinBox.setValue(destinationData.conditionValue)
        self.nameWidget.lineEdit.setText(item)

    def inputSignal_destinationsUpdated(self, items):
        print('inputSignal_destinationsPicked,', items)

    def inputSignal_altDestinationsUpdated(self, items):
        print('inputSignal_altDestinationsPicked,', items)

    def inputSignal_nameChanged(self, name):
        print('inputSignal_nameChanged,', name)

    def inputSignal_attributehanged(self, attribute):
        print('inputSignal_namgeChanged,', attribute)

    def inputSignal_conditionhanged(self, value):
        print('inputSignal_conditionhanged,', value)

    def addWalk(self, direction=str()):
        outData = dict()
        if not self.destinationsWidget.currentItems():
            return pm.warning('No destinations')
        if not self.altDestinationsWidget.currentItems():
            return pm.warning('No alt destinations')
        if not self.conditionAttrWidget.lineEdit.text():
            return pm.warning('No valid attribute')
        outData['destination'] = self.destinationsWidget.currentItems()
        outData['destinationAlt'] = self.altDestinationsWidget.currentItems()
        outData['conditionAttribute'] = self.conditionAttrWidget.lineEdit.text()
        outData['conditionValue'] = self.conditionWidget.spinBox.value()
        outData['name'] = self.controlWidget.lineEdit.text() + '__' + direction

        self.creator.addDestination(name=outData['name'],
                                    destination=outData['destination'],
                                    destinationAlt=outData['destinationAlt'],
                                    conditionAttribute=outData['conditionAttribute'],
                                    conditionValue=outData['conditionValue'])
        for control in self.controls:
            self.creator.setControlDestination(control,
                                               direction=direction,
                                               destination=outData['name'])

        self.pickwalkWindow.saveLibrary()
        self.pickwalkWindow.loadLibraryForCurrent()
        self.pickwalk.loadWalkLibrary()
        self.pickwalk.getAllPickwalkMaps()
        self.pickwalk.initialiseWalkData()


class mirrorPickwalkWidget(QFrame):
    pressed = Signal(None)
    changed = Signal(str)
    fromInputOption = pm.optionVar.get('fromInputOption', '_L')
    toInputOption = pm.optionVar.get('toInputOption', '_R')
    mirrorPressed = Signal(str, str)

    def __init__(self, *args, **kwargs):
        QFrame.__init__(self, *args, **kwargs)
        self.setMaximumWidth(420)
        self.mainLayout = QVBoxLayout()
        self.mainLayout.setContentsMargins(2, 2, 2, 2)

        self.layout = QHBoxLayout()
        # self.setStyleSheet(getqss.getStyleSheet())
        self.setStyleSheet("QFrame {"
                           "border-width: 2;"
                           "border-radius: 4;"
                           "border-style: solid;"
                           "border-color: #222222}"
                           )

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.mainLayout)
        self.title = QLabel('Mirror Selected Controls')
        self.title.setStyleSheet("QLabel {"
                                 "border-width: 0;"
                                 "border-radius: 4;"
                                 "border-style: solid;"
                                 "border-color: #222222;"
                                 "font-weight: bold; font-size: 12px;}"
                                 )
        self.mainLayout.addWidget(self.title)
        self.mainLayout.addLayout(self.layout)

        self.fromLabel = QLabel('Sides')

        self.fromLabel.setStyleSheet("QFrame {"
                                     "border-width: 0;"
                                     "border-radius: 0;"
                                     "border-style: solid;"
                                     "border-color: #222222}"
                                     )
        self.fromInput = QLineEdit(self.fromInputOption)
        self.toInput = QLineEdit(self.toInputOption)
        self.mirrorBtn = QPushButton('Mirror selection')
        self.mirrorBtn.clicked.connect(self.sendMirrorSignal)
        self.layout.addWidget(self.fromLabel)
        self.layout.addWidget(self.fromInput)
        self.layout.addWidget(self.toInput)
        self.layout.addWidget(self.mirrorBtn)

        self.fromLabel.setFixedWidth(48)
        # self.mainLayout.addStretch(1)

        # events
        self.fromInput.textChanged.connect(self.fromChanged)

        # line edit input mask
        # reg_ex = QRegExp("[a-z-A-Z0123456789_,]+")
        # fromInput_validator = QRegExpValidator(reg_ex, self.fromInput)
        # self.fromInput.setValidator(fromInput_validator)

    def sendMirrorSignal(self):
        self.mirrorPressed.emit(self.fromInput.text(), self.toInput.text())

    def fromChanged(self, lineEdit):
        pass

    def toChanged(self, lineEdit):
        pass

    @Slot()
    def sendChangedSignal(self):
        self.changed.emit(self.currentColour, self.paletteIndex)

    @Slot()
    def sendPressedSignal(self):
        self.pressed.emit()

    def on_clicked(self, event):
        if event.button() == Qt.LeftButton:
            self.sendSelectedSignal()
            return
        elif event.button() == Qt.RightButton:
            color = QColorDialog.getColor()
            if color.isValid():
                self.setColor(color)
                self.sendChangedSignal()
            return
        return


class pickwalkRigAssignemtWindow(QMainWindow):

    def __init__(self):
        super(pickwalkRigAssignemtWindow, self).__init__(
            parent=wrapInstance(int(omUI.MQtUtil.mainWindow()), QWidget))
        # DATA
        self.setMinimumWidth(400)
        self.setMinimumHeight(400)
        self.walkDataLibrary = WalkDataLibrary()

        self.defaultPickwalkDir = Pickwalk().defaultPickwalkDir
        if not os.path.isdir(self.defaultPickwalkDir):
            os.mkdir(self.defaultPickwalkDir)
        self.libraryFile = pm.optionVar.get('pickwalkLibrary', 'pickwalkLibraryData.json')
        self.libraryFilePath = os.path.join(self.defaultPickwalkDir, self.libraryFile)

        if not os.path.isfile(self.libraryFilePath):
            self.createLibrary()
        else:
            self.walkDataLibrary.load(self.libraryFilePath)
        self.currentMap = None
        self.currentIgnoredRig = None
        self.currentRig = None

        # Main Widgets
        # setup stylesheet
        self.setStyleSheet(getqss.getStyleSheet())
        self.setWindowTitle('tbPickwwalkAssignment')

        main_widget = QWidget()

        self.setCentralWidget(main_widget)

        self.main_layout = QHBoxLayout()
        self.left_layout = QHBoxLayout()
        self.right_layout = QVBoxLayout()
        self.main_layout.addLayout(self.left_layout)
        self.main_layout.addLayout(self.right_layout)
        main_widget.setLayout(self.main_layout)

        menu = self.menuBar()
        edit_menu = menu.addMenu('&File')

        self.addReferenceButton = QPushButton('Add Rig To Map')
        self.addReferenceButton.setToolTip(ToolTip_AddRigToMap)
        self.addReferenceButton.clicked.connect(self.addRigToMap)
        self.removeeferenceButton = QPushButton('Remove Rig From Map')
        self.removeeferenceButton.clicked.connect(self.removeRigFromMap)
        self.assignIgnoredRigButton = QPushButton('Assign Ignored Rig to Map')
        self.assignIgnoredRigButton.clicked.connect(self.addRigToFromIgnoreListMap)

        self.pickwalkMapTree = QTreeSingleViewWidget(label='Pickwalk Maps')
        self.referencedRigsTree = QTreeSingleViewWidget(label='Referenced Rigs')
        self.ignoredRigsTree = QTreeSingleViewWidget(label='Ignored Rigs')
        self.left_layout.addWidget(self.pickwalkMapTree)
        self.right_layout.addWidget(self.referencedRigsTree)
        self.right_layout.addWidget(self.addReferenceButton)
        self.right_layout.addWidget(self.removeeferenceButton)
        self.right_layout.addWidget(self.ignoredRigsTree)
        self.right_layout.addWidget(self.assignIgnoredRigButton)

        self.pickwalkMapTree.pressedSignal.connect(self.mapClicked)
        self.referencedRigsTree.pressedSignal.connect(self.referenceClicked)
        self.ignoredRigsTree.pressedSignal.connect(self.ignoredClicked)

        self.getAllPickwalkMaps()
        self.updateUI()

    def referenceClicked(self, item):
        self.currentRig = item

    def ignoredClicked(self, item):
        self.currentIgnoredRig = item

    def mapClicked(self, item):
        self.currentMap = item
        self.updateReferencedRigView()

    def updateReferencedRigView(self):
        self.referencedRigsTree.updateView(self.walkDataLibrary.rigMapDict[self.currentMap])

    def browseToFile(self):
        fname = QFileDialog.getOpenFileName(self, 'Open file',
                                            cmds.workspace(q=True, directory=True),
                                            "Maya files (*.ma *.mb)")
        return fname[0] or None

    def addRigToFromIgnoreListMap(self):
        if not self.currentMap:
            return
        if not self.currentIgnoredRig:
            return
        self.walkDataLibrary.assignRig(self.currentMap, self.currentIgnoredRig)

        self.walkDataLibrary.save(self.libraryFilePath)
        Pickwalk().loadWalkLibrary()
        self.referencedRigsTree.appendItem(self.currentIgnoredRig)
        self.ignoredRigsTree.removeItem(self.currentIgnoredRig)

    def removeRigFromMap(self):
        if not self.currentMap:
            return
        if not self.currentRig:
            return
        self.walkDataLibrary.ignoreRig(self.currentRig)
        self.referencedRigsTree.removeItem(self.currentRig)
        self.ignoredRigsTree.appendItem(self.currentRig)
        self.walkDataLibrary.save(self.libraryFilePath)

    def addRigToMap(self):
        if not self.currentMap:
            return
        fname = self.browseToFile()
        if not fname:
            return None
        baseName = os.path.basename(fname)

        self.walkDataLibrary.assignRig(self.currentMap, baseName.split('.')[0])

        self.walkDataLibrary.save(self.libraryFilePath)
        Pickwalk().loadWalkLibrary()
        self.ignoredRigsTree.removeItem(baseName.split('.')[0])
        self.pickwalkMapTree.appendItem(baseName.split('.')[0])

    def updateUI(self):
        self.pickwalkMapTree.CLS = self.walkDataLibrary
        self.pickwalkMapTree.updateView(self.walkDataLibrary.rigMapDict.keys())
        self.ignoredRigsTree.updateView(self.walkDataLibrary.ignoredRigs)

    def createLibrary(self):
        self.walkDataLibrary.save(self.libraryFilePath)
        pm.optionVar['pickwalkLibrary'] = self.libraryFile

    def getAllPickwalkMaps(self):
        jsonFiles = list()
        for filename in os.listdir(self.defaultPickwalkDir):
            if filename.endswith(".json"):
                if os.path.basename(filename) == self.libraryFile:
                    continue
                jsonFiles.append(os.path.join(self.defaultPickwalkDir, filename))
        for filename in jsonFiles:
            mapName = os.path.basename(filename).split('.')[0]
            if mapName not in self.walkDataLibrary.rigMapDict.keys():
                self.walkDataLibrary.rigMapDict[mapName] = list()

        statinfo = os.access(self.libraryFilePath, os.W_OK)
        if statinfo:
            self.walkDataLibrary.save(self.libraryFilePath)


class pickwalkMainWindow(QMainWindow):
    loop = False
    reciprocate = True
    endOnSelf = False

    activeObject = None
    title = 'tbPickwwalkSetup'

    def __init__(self, autoLoad=True):
        super(pickwalkMainWindow, self).__init__(parent=wrapInstance(int(omUI.MQtUtil.mainWindow()), QWidget))
        # DATA
        self.defaultDir = pm.optionVar.get('pickwalkDir',
                                           os.path.join(os.path.normpath(os.path.dirname(__file__)),
                                                        'pickwalkData'))
        if not os.path.isdir(self.defaultDir):
            os.mkdir(self.defaultDir)

        self.pickwalkCreator = PickwalkCreator()
        self.resize(948, self.height())
        # Main Widgets
        # setup stylesheet
        self.setStyleSheet(getqss.getStyleSheet())
        self.setWindowTitle('tbPickwwalkSetup')
        self.titleLabel = QLabel('No current template')
        self.lockState = False

        self.hiddenLayout = QHBoxLayout()

        self.currentControl = None
        self.currentDestination = None
        self.currentTargetUp = None
        self.currentTargetDown = None
        self.currentTargetLeft = None
        self.currentTargetRight = None

        main_widget = QWidget()

        self.setCentralWidget(main_widget)

        self.superLayout = QVBoxLayout()
        self.main_layout = QHBoxLayout()
        self.left_layout = QHBoxLayout()
        self.left_layout.addLayout(self.left_layout)

        self.right_layout = QVBoxLayout()
        self.superLayout.addWidget(self.titleLabel)
        self.superLayout.addLayout(self.main_layout)
        self.main_layout.addLayout(self.left_layout)
        self.main_layout.addLayout(self.right_layout)
        main_widget.setLayout(self.superLayout)

        menu = self.menuBar()
        file_menu = menu.addMenu('&File')
        option_menu = menu.addMenu('&Options')
        view_menu = menu.addMenu('&View')

        add_action = QAction('Add new library', self)
        add_action.setShortcut('Ctrl+N')
        file_menu.addAction(add_action)
        add_action.triggered.connect(self.newLibrary)

        load_action = QAction('Load (replace)', self)
        load_action.setShortcut('Ctrl+O')
        file_menu.addAction(load_action)
        load_action.triggered.connect(self.loadLibrary)

        load_action = QAction('Load map for current rig', self)
        load_action.setShortcut('Ctrl+C')
        file_menu.addAction(load_action)
        load_action.triggered.connect(self.loadLibraryForCurrent)

        merge_action = QAction('load (merge)', self)
        merge_action.setShortcut('Ctrl+M')
        file_menu.addAction(merge_action)
        merge_action.triggered.connect(self.appendLibrary)

        mergeSelected_action = QAction('load to selected', self)
        file_menu.addAction(mergeSelected_action)
        mergeSelected_action.triggered.connect(self.loadLibraryToSelection)

        save_action = QAction('Save', self)
        save_action.setShortcut('Ctrl+S')
        file_menu.addAction(save_action)
        save_action.triggered.connect(self.saveLibrary)

        saveAs_action = QAction('Save AS', self)
        saveAs_action.setShortcut('Ctrl+Shift+S')
        file_menu.addAction(saveAs_action)
        saveAs_action.triggered.connect(self.saveAsLibrary)

        assign_action = QAction('Assign to selected rig', self)
        file_menu.addAction(assign_action)
        assign_action.triggered.connect(self.assignToSelectedRig)

        open_action = QAction('Open pickwalk data location', self)
        open_action.triggered.connect(self.openDataFolder)
        file_menu.addAction(open_action)


        self.saveOnEdit_action = QAction('Save On Edit', self)
        self.saveOnEdit_action.setCheckable(True)
        self.saveOnEdit_action.triggered.connect(self.toggleSaveOnEdit)
        option_menu.addAction(self.saveOnEdit_action)



        '''
        nodeGrapherModeSimple.svg
        nodeGrapherModeConnected.svg
        nodeGrapherModeAll.svg
        '''
        simple_action = QAction('Simple mode', self)
        simple_action.triggered.connect(self.setSimpleMode)
        simple_action.setShortcut('Ctrl+1')
        simple_action.setIcon(QIcon(QPixmap(':/{}'.format('nodeGrapherModeSimple.svg'))))
        view_menu.addAction(simple_action)

        medium_action = QAction('Context mode', self)
        medium_action.triggered.connect(self.setMediumMode)
        medium_action.setShortcut('Ctrl+2')
        medium_action.setIcon(QIcon(QPixmap(':/{}'.format('nodeGrapherModeConnected.svg'))))
        view_menu.addAction(medium_action)

        full_action = QAction('Full mode', self)
        full_action.triggered.connect(self.setDetailMode)
        full_action.setShortcut('Ctrl+3')
        full_action.setIcon(QIcon(QPixmap(':/{}'.format('nodeGrapherModeAll.svg'))))
        view_menu.addAction(full_action)

        self.mainPickWidget = pickDirectionWidget(self)
        # self.contextPickWidget = pickContextDirectionWidget()
        self.controlListWidget = ControlListWidget(CLS=self.pickwalkCreator, label='Controls ::')
        self.destinationListWidget = DestinationListWidget(CLS=self.pickwalkCreator, label='Destinations')
        self.mirrorWidget = mirrorPickwalkWidget()
        self.contextWidget = contextPickwalkWidget()

        self.right_layout.addWidget(self.mainPickWidget)
        # self.right_layout.addWidget(self.contextPickWidget)
        self.right_layout.addWidget(self.contextWidget)
        self.right_layout.addWidget(self.mirrorWidget)
        # self.right_layout.addStretch()
        # self.left_layout.addStretch(0)
        self.main_layout.addWidget(self.destinationListWidget)
        self.main_layout.addWidget(self.controlListWidget)

        # dummy = QVBoxLayout()
        # self.right_layout.addLayout(dummy)
        # self.left_layout.addStretch()
        # connect events
        self.controlListWidget.newDestinationSignal.connect(self.inputSignal_dirFromControlTreeView)
        self.controlListWidget.newConditionDestinationSignal.connect(
            self.inputSignal_conditionDirFromControlTreeView)
        self.controlListWidget.getFromRigSignal.connect(self.inputSignal_getFromRig)
        self.destinationListWidget.applySignal.connect(self.inputSignal_applyDestinationToCurrent)
        self.destinationListWidget.selectedSignal.connect(self.inputSignal_selectConditionalDestination)
        self.destinationListWidget.pressedSignal.connect(self.inputSignal_displayConditionalDestination)
        self.destinationListWidget.pressedSignal.connect(
            self.contextWidget.destinationsWidget.recieveMainDestinationClicked)
        self.destinationListWidget.pressedSignal.connect(
            self.contextWidget.altDestinationsWidget.recieveMainDestinationClicked)
        # self.contextPickWidget.directionPressedObjectSignal.connect(self.inputSignal_setConditionalDestination)
        self.mainPickWidget.setActiveObjectSignal.connect(self.inputSignal_activeObjectSet)
        self.mainPickWidget.applyButtonPressedSignal.connect(self.inputSignal_applyPickwalk)

        self.mainPickWidget.upDownSignal.connect(self.inputSignal_quickUpDown)
        self.mainPickWidget.leftRightSignal.connect(self.inputSignal_quickLeftRight)
        self.mainPickWidget.downMultiSignal.connect(self.inputSignal_quickDownToMulti)
        self.mainPickWidget.upMultiSignal.connect(self.inputSignal_quickUpFromMulti)

        self.mainPickWidget.setLockStateSignal.connect(self.setLockState)
        self.mainPickWidget.directionPressedObjectSignal.connect(self.addPickwalk)
        self.mainPickWidget.loopChanged.connect(self.inputSignal_loopChanged)
        self.mainPickWidget.reciprocateChanged.connect(self.inputSignal_reciprocateChanged)
        self.mainPickWidget.endOnSelfChanged.connect(self.inputSignal_endOnSelfChanged)
        self.contextWidget.destinationAdded.connect(self.inputSignal_destinationAdded)
        self.mirrorWidget.mirrorPressed.connect(self.inputSignal_mirrorSelection)

        # self.SCRIPT_JOB_NUMBER = cmds.scriptJob(event=['SelectionChanged', self.onSelectionChange], protected=True)

        self.setSimpleMode()
        if autoLoad:
            self.loadLibraryForCurrent()

    def closeEvent(self, event):
        msg = QMessageBox()
        msg.setStyleSheet(getqss.getStyleSheet())
        msg.setIcon(QMessageBox.Warning)

        msg.setText("Overwrite existing data?")
        msg.setWindowTitle("Existing file warning")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)

        quit_msg = "You may have unsaved changes, are you sure want to close"
        reply = QMessageBox.question(self, 'Message',
                                     quit_msg, QMessageBox.Yes, QMessageBox.No)

        if reply == QMessageBox.Yes:
            # Clean up the script job stuff prior to closing the dialog.
            # cmds.scriptJob(kill=self.SCRIPT_JOB_NUMBER, force=True)
            super(pickwalkMainWindow, self).closeEvent(event)
            event.accept()
        else:
            event.ignore()

    def onSelectionChange(self):
        if not self.lockState:
            self.mainPickWidget.displayCurrentData(self.pickwalkCreator.walkData)

        # self.contextPickWidget.setActiveObject()

    def browseToFile(self):
        fname = QFileDialog.getOpenFileName(self, 'Open file',
                                            Pickwalk().defaultPickwalkDir,
                                            "Pickwalk files (*.json)")
        return fname[0] or None

    def newLibrary(self):
        self.pickwalkCreator = PickwalkCreator()
        self.refreshUI()
        self.setWindowTitle('tbPickwwalkSetup :: untitled')
        self.titleLabel.setText('current template :: untitled')

    def getCurrentRig(self):
        refName = None
        mapName = None
        fname = None
        sel = cmds.ls(sl=True)

        refName = self.getReferenceName(sel)
        pickwalk = Pickwalk()
        if refName in pickwalk.walkDataLibrary._fileToMapDict.keys():
            mapName = pickwalk.walkDataLibrary._fileToMapDict[refName]
            fname = os.path.join(pickwalk.defaultPickwalkDir, mapName + '.json')
        return fname

    def getReferenceName(self, sel):
        refName = None
        if sel:
            refState = cmds.referenceQuery(sel[0], isNodeReferenced=True)
            if refState:
                # if it is referenced, check against pickwalk library entries
                refName = cmds.referenceQuery(sel[0], filename=True, shortName=True).split('.')[0]
            else:
                # might just be working in the rig file itself
                refName = cmds.file(query=True, sceneName=True, shortName=True).split('.')[0]
        else:
            refName = cmds.file(query=True, sceneName=True, shortName=True).split('.')[0]
        return refName

    def loadLibraryForCurrent(self):
        # TODO - implement this to look at the main walk library and open the
        # TODO - correct map file
        #
        fname = self.getCurrentRig()
        if not fname:
            fname = self.browseToFile()
        if not fname:
            return None

        self.pickwalkCreator.load(fname)
        self.refreshUI()

        self.setTitleLabel(fname)

    def setTitleLabel(self, fname):
        if isinstance(fname, list):
            fname = fname[0]
        lbl = os.path.normpath(fname).split('\\')[-1]
        self.titleLabel.setText('current template :: ' + lbl)

    def loadLibrary(self):
        fname = self.browseToFile()
        if not fname:
            return None
        self.pickwalkCreator.walkData = WalkData()
        self.pickwalkCreator.load(fname)
        self.refreshUI()
        # self.setWindowTitle('tbPickwwalkSetup :: %s' % fname)
        self.setTitleLabel(fname)

    def appendLibrary(self):
        fname = self.browseToFile()
        if not fname:
            return None
        self.pickwalkCreator.load(fname)
        self.refreshUI()

    def loadLibraryToSelection(self):
        fname = self.browseToFile()
        if not fname:
            return None
        self.pickwalkCreator.load(fname, controlFilter=cmds.ls(sl=True))
        self.refreshUI()

    def saveLibrary(self):
        if not self.pickwalkCreator.walkData._filePath:
            self.saveAsLibrary()
        else:
            self.pickwalkCreator.walkData.save(self.pickwalkCreator.walkData._filePath)
        Pickwalk()
        self.refreshUI()

    def saveAsLibrary(self):
        save_filename = Pickwalk().saveAsLibrary()
        self.setWindowTitle('tbPickwwalkSetup :: %s' % save_filename)
        return os.path.basename(save_filename)

    def assignToSelectedRig(self):
        pickwalk = Pickwalk()
        if not self.pickwalkCreator.walkData.name:
            return cmds.warning('No current map')
        sel = cmds.ls(sl=True)

        fname = self.getReferenceName(sel)

        if not fname:
            fname = self.browseToFile()
        if not fname:
            return None
        baseName = os.path.basename(fname)

        pickwalk.walkDataLibrary.assignRig(self.pickwalkCreator.walkData.name, baseName.split('.')[0])
        pickwalk.savePickwalkLibraryMap()
        pickwalk.loadWalkLibrary()
        pickwalk.forceReloadData()

    def overwriteQuery(self):
        msg = QMessageBox()
        msg.setStyleSheet(getqss.getStyleSheet())
        msg.setIcon(QMessageBox.Warning)

        msg.setText("Overwrite existing data?")
        msg.setWindowTitle("Existing file warning")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        return msg

    def refreshUI(self):
        self.controlListWidget.CLS = self.pickwalkCreator
        self.destinationListWidget.CLS = self.pickwalkCreator
        self.mainPickWidget.displayCurrentData(self.pickwalkCreator.walkData, self.activeObject)
        self.updateTreeView()

    def keyPressEvent(self, event):
        return super(pickwalkMainWindow, self).keyPressEvent(event)

    def inputSignal_applyDestinationToCurrent(self, item):
        sel = cmds.ls(sl=True)
        if not sel:
            return
        for s in sel:
            self.pickwalkCreator.replaceDestination(original=s.split(':')[-1], new=item)
        self.saveOnUpdate()

    def inputSignal_selectConditionalDestination(self, item):
        self.currentDestination = item

    def inputSignal_displayConditionalDestination(self, item):
        self.contextWidget.populate(item, self.pickwalkCreator.walkData.destinations[item])

    def inputSignal_conditionDirFromControlTreeView(self, item):
        index = self.destinationListWidget.treeView.selectedIndexes()[0]
        if not index:
            return
        destinationItem = self.destinationListWidget.model.itemFromIndex(
            self.destinationListWidget.proxyModel.mapToSource(index))
        # 'new destination item is,', item.text()
        self.pickwalkCreator.setControlDestination(item.control,
                                                   direction=item.direction,
                                                   destination=destinationItem.text())
        item.setText(destinationItem.text())
        self.saveOnUpdate()

    def inputSignal_dirFromControlTreeView(self, control, direction, destination):
        if len(destination) > 1:
            # multiple objects, quick set up destination
            outData = dict()
            outData['destination'] = [x.split(':')[-1] for x in destination]
            outData['destinationAlt'] = list()
            outData['conditionAttribute'] = str()
            outData['conditionValue'] = 0.5
            outData['name'] = destination[0].split(':')[-1] + '_in'
            self.contextWidget.destinationAdded.emit(outData)
        else:
            # single object, add as direct target
            self.pickwalkCreator.setControlDestination(control,
                                                       direction=direction,
                                                       destination=destination[0].split(':')[-1])
        self.saveOnUpdate()

    def setLockState(self, bool):
        self.lockState = bool

    def inputSignal_quickUpFromMulti(self):
        sel = cmds.ls(selection=True, type='transform')
        if len(sel) > 1:
            # pm.warning('inputSignal_quickUpFromMulti')
            control = sel[0].split(':')[-1]
            targets = [s.split(':')[-1] for s in sel[1:]]
            for s in targets:
                self.pickwalkCreator.setControlDestination(s,
                                                           direction='up',
                                                           destination=control)
            self.updateTreeView()
            self.saveOnUpdate()
            return

    def inputSignal_quickDownToMulti(self):
        sel = cmds.ls(selection=True, type='transform')
        if len(sel) > 1:
            # pm.warning('inputSignal_quickDownToMulti')
            control = sel[0].split(':')[-1]
            targets = [s.split(':')[-1] for s in sel[1:]]
            name = control + '_' + targets[0] + '_mult'
            self.pickwalkCreator.addDestination(name=name,
                                                destination=targets,
                                                destinationAlt=list(),
                                                conditionAttribute=str(),
                                                conditionValue=0.5)
            self.pickwalkCreator.setControlDestination(control,
                                                       direction='down',
                                                       destination=name)
            self.updateTreeView()
            self.saveOnUpdate()
            return

    def inputSignal_quickLeftRight(self):
        sel = cmds.ls(selection=True, type='transform')
        if len(sel) > 1:
            # pm.warning('inputSignal_quickLeftRight')
            self.pickwalkCreator.addPickwalkChain(controls=sel,
                                                  direction='left',
                                                  loop=True,
                                                  reciprocate=True,
                                                  endOnSelf=False)
            self.updateTreeView()
            self.saveOnUpdate()
            return

    def inputSignal_quickUpDown(self):
        sel = cmds.ls(selection=True, type='transform')
        if len(sel) > 1:
            # pm.warning('inputSignal_quickUpDown')
            self.pickwalkCreator.addPickwalkChain(controls=sel,
                                                  direction='down',
                                                  loop=False,
                                                  reciprocate=True,
                                                  endOnSelf=True)
            self.updateTreeView()
            self.saveOnUpdate()
            return

    @Slot()
    def inputSignal_setConditionalDestination(self, direction, control, destination):
        self.pickwalkCreator.setControlDestination(control,
                                                   direction=direction,
                                                   destination=destination)
        self.updateTreeView()
        self.saveOnUpdate()
        return

    @Slot()
    def inputSignal_applyPickwalk(self, control, up, down, left, right):
        self.pickwalkCreator.setControlDestination(control,
                                                   direction='up',
                                                   destination=up)
        self.pickwalkCreator.setControlDestination(control,
                                                   direction='down',
                                                   destination=down)
        self.pickwalkCreator.setControlDestination(control,
                                                   direction='left',
                                                   destination=left)
        self.pickwalkCreator.setControlDestination(control,
                                                   direction='right',
                                                   destination=right)
        self.updateTreeView()
        self.saveOnUpdate()

    def saveOnUpdate(self):
        if pm.optionVar.get(saveOnUpdateOption, False):
            self.saveLibrary()

    def inputSignal_activeObjectSet(self):
        sel = cmds.ls(sl=True)
        if not sel:
            return
        self.activeObject = sel[0].split(':')[-1]
        self.mainPickWidget.objectWidget.currentObjLabel.setText(self.activeObject)
        self.mainPickWidget.displayCurrentData(self.pickwalkCreator.walkData, self.activeObject)

        for control in sel:
            self.pickwalkCreator.addControl(control)
        self.updateTreeView()

    def updateTreeView(self):
        self.controlListWidget.updateView()
        self.destinationListWidget.updateView()

    def inputSignal_loopChanged(self, state):
        self.loop = state

    def inputSignal_reciprocateChanged(self, state):
        self.reciprocate = state

    def inputSignal_endOnSelfChanged(self, state):
        self.endOnSelf = state

    def inputSignal_mirrorSelection(self, sideA, sideB):
        sel = cmds.ls(selection=True, type='transform')
        if not sel:
            return pm.warning('No selection')
        for s in sel:
            self.pickwalkCreator.mirror(s.split(':')[-1], [sideA, sideB])
        self.updateTreeView()

    def inputSignal_destinationAdded(self, input):
        self.pickwalkCreator.addDestination(name=input.get('name', 'defaultName'),
                                            destination=input.get('destination', list()),
                                            destinationAlt=input.get('destinationAlt', list()),
                                            conditionAttribute=input.get('conditionAttribute', str()),
                                            conditionValue=input.get('conditionValue', 0.5))
        self.destinationListWidget.updateView()
        self.saveOnUpdate()

    def inputSignal_getFromRig(self):
        for s in cmds.ls(sl=True):
            self.pickwalkCreator.getNodeInfoFromRig(s)
        self.refreshUI()

    def addPickwalk(self, direction):
        sel = cmds.ls(selection=True, type='transform')
        if not sel:
            return pm.warning('No selection')
        if self.lockState:
            if not self.activeObject:
                return pm.warning('Unable to add single destination with no active object')
            # there is an active (locked object)
            if len(sel) > 1:
                # multiple objects, quick set up destination
                self.pickwalkCreator.addDestination(name=sel[0].split(':')[-1] + '_in',
                                                    destination=[x.split(':')[-1] for x in sel],
                                                    destinationAlt=list(),
                                                    conditionAttribute=str(),
                                                    conditionValue=0.5)
                self.pickwalkCreator.setControlDestination(self.activeObject,
                                                           direction=direction,
                                                           destination=sel[0].split(':')[-1] + '_in')
            else:
                # single object, add as direct target
                self.pickwalkCreator.setControlDestination(self.activeObject,
                                                           direction=direction,
                                                           destination=sel[0].split(':')[-1])

            self.inputSignal_dirFromControlTreeView(self.activeObject, direction, sel)
            self.updateTreeView()
            return

        if len(sel) > 1:
            # pm.warning('Adding chain style')
            self.pickwalkCreator.addPickwalkChain(controls=sel,
                                                  direction=direction,
                                                  loop=self.loop,
                                                  reciprocate=self.reciprocate,
                                                  endOnSelf=self.endOnSelf)
            self.updateTreeView()
            return

        if not self.activeObject:
            return pm.warning('Unable to add single destination with no active object')
        # pm.warning('Adding single style')
        self.pickwalkCreator.setControlDestination(self.activeObject,
                                                   direction=direction,
                                                   destination=sel[0])
        self.updateTreeView()
        self.updateTreeView()
        self.saveOnUpdate()
        return

    def toggleSaveOnEdit(self):
        pm.optionVar[saveOnUpdateOption] = self.saveOnEdit_action.isChecked()

    def openDataFolder(self):
        os.startfile(self.defaultDir)

    def setSimpleMode(self):
        self.mainPickWidget.setVisible(True)
        # self.contextPickWidget.setVisible(False)
        self.controlListWidget.setVisible(False)
        self.destinationListWidget.setVisible(False)
        self.mirrorWidget.setVisible(True)
        self.contextWidget.setVisible(False)

        self.mainPickWidget.upBtn.contextButton.hide()
        self.mainPickWidget.downBtn.contextButton.hide()
        self.mainPickWidget.leftBtn.contextButton.hide()
        self.mainPickWidget.rightBtn.contextButton.hide()

        self.update()
        self.resize(self.width() * 0.5, self.height() * 0.5)
        self.adjustSize()

    def setMediumMode(self):
        # self.mainPickWidget.setVisible(False)
        # self.contextPickWidget.setVisible(True)
        self.destinationListWidget.setVisible(True)
        self.destinationListWidget.applyButton.setVisible(False)
        self.controlListWidget.setVisible(False)
        self.mirrorWidget.setVisible(True)
        self.contextWidget.setVisible(True)

        self.mainPickWidget.upBtn.contextButton.show()
        self.mainPickWidget.downBtn.contextButton.show()
        self.mainPickWidget.leftBtn.contextButton.show()
        self.mainPickWidget.rightBtn.contextButton.show()

        self.update()
        self.resize(self.width() * 0.5, self.height() * 0.5)
        self.adjustSize()

    def setDetailMode(self):
        self.mainPickWidget.setVisible(True)
        # self.contextPickWidget.setVisible(True)
        self.controlListWidget.setVisible(True)
        self.destinationListWidget.setVisible(True)
        self.destinationListWidget.applyButton.setVisible(True)
        self.mirrorWidget.setVisible(True)
        self.contextWidget.setVisible(True)

        self.mainPickWidget.upBtn.contextButton.show()
        self.mainPickWidget.downBtn.contextButton.show()
        self.mainPickWidget.leftBtn.contextButton.show()
        self.mainPickWidget.rightBtn.contextButton.show()

        self.update()
        self.resize(self.width() * 0.5, self.height() * 0.5)
        self.adjustSize()


class PickWalkObjectDialog(BaseDialog):
    assignSignal = Signal(str, str, str, list)
    conditionSignal = Signal(str, str, str, list)

    def __init__(self, direction, namespace, walkObject, parent=None, title='title', text='test', altText='alt text'):
        super(PickWalkObjectDialog, self).__init__(parent=parent, title=title, text=text)
        self.direction = direction
        self.namespace = namespace
        self.walkObject = walkObject
        self.result = str()
        self.setFixedWidth(260)
        self.buttonBox = QDialogButtonBox()
        conditionButton = self.buttonBox.addButton("Add Condition", QDialogButtonBox.ActionRole)
        self.buttonBox.addButton("Add Basic", QDialogButtonBox.AcceptRole)
        self.buttonBox.addButton("Cancel", QDialogButtonBox.RejectRole)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        conditionButton.clicked.connect(lambda: self.makeCondition())
        self.infoLabel = QLabel(altText)
        self.itemLabel = QLineEdit()  # TODO add the inline button to this (from path tool)
        self.cle_action_pick = self.itemLabel.addAction(QIcon(":/targetTransfoPlus.png"), QLineEdit.TrailingPosition)
        self.cle_action_pick.setToolTip(
            'Pick path control from selection\nThis object will be used to generate your path.')
        self.cle_action_pick.triggered.connect(self.pickObject)

        # self.layout.addWidget(self.infoLabel)
        self.layout.addWidget(self.itemLabel)

        self.mainLayout.addWidget(self.buttonBox)

    def makeCondition(self):
        self.conditionSignal.emit(self.direction, self.namespace, self.walkObject, self.result)
        self.close()

    def pickObject(self):
        sel = pm.ls(sl=True)
        if not sel:
            return
        self.itemLabel.setText(str(sel[0]))
        self.result = sel

    def accept(self):
        self.assignSignal.emit(self.direction, self.namespace, self.walkObject, self.result)
        super(PickWalkObjectDialog, self).accept()

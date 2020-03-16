import copy
import datetime
import os
import functools
from random import shuffle
import sys
import time
from pathlib import Path

import unittest
# import cProfile

import pygame.midi

# from music21 import *

lastUpdateTime = time.time()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class Config:
    progressUpdateSeconds = 5
    lastUpdateTime = 0

    maxMelodiesPerFinalIntervalSubset = 100

    minMelodyIntervals = 4
    maxMelodyIntervals = 14
    maxMelodyHeight = 19
    maxDirectionChanges = 14

    midiA0 = 21
    midiE3 = 52
    midiC4 = 60
    midiC8 = 108

    vocalRanges = {
        # "name"         : ( "low", "mid", "high" ),
        "soprano": ("C4", "B4", "G5"),
        "mezzo-soprano": ("A3", "G4", "F5"),
        "alto": ("G3", "F4", "D5"),
        "tenor": ("C3", "B3", "A4"),
        "baritone": ("G2", "F3", "E4"),
        "bass": ("F2", "E3", "C4"),
    }


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class Tone:

    def __init__(self, midiNote):
        self.midiNote = midiNote

    noteToSpelling = {
        0: "A", 1: "A♯", 2: "B", 3: "C", 4: "C♯", 5: "D",
        6: "D♯", 7: "E", 8: "F", 9: "F♯", 10: "G", 11: "G♯"}

    spellingToNote = {
        "A": 0, "A♯": 1, "B♭": 1, "B": 2, "C♭": 2, "B♯": 3,
        "C": 3, "C♯": 4, "D♭": 4, "D": 5, "D♯": 6, "E♭": 6,
        "E": 7, "F♭": 7, "E♯": 8, "F": 8, "F♯": 9, "G♭": 9,
        "G": 10, "G♯": 11, "A♭": 11}

    def getNoteNumber(self):    return self.midiNote - Config.midiA0

    def getOctave(self):        return (self.getNoteNumber() + 12 - 3) // 12

    def getSpelling(self):      return self.noteToSpelling[self.getNoteNumber() % 12]

    def isSharp(self):          return self.getSpelling()[-1] == '♯'

    def getLetter(self):        return self.getSpelling()[0]

    def getSpellingAndOctave(self):
        note = self.getNoteNumber()
        octave = (note + 12 - 3) // 12
        name = self.noteToSpelling[note % 12]
        return name + str(self.getOctave())


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class Melody:
    possibleFirstIntervals = \
        (-7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7)

    possibleLastIntervals = \
        (-7, -4, -3, -2, -1, 1, 2, 5,)

    possibleFollowingIntervals = {
        -7: (-2, -1, 1, 2, 5, 6,),
        -6: (-2, -1, 1, 2, 4, 5, 7),
        -5: (-2, -1, 1, 2, 3, 4, 6, 7),
        -4: (-2, -1, 1, 2, 3, 5, 6,),
        -3: (-2, -1, 1, 2, 4, 5,),
        -2: (-7, -6, -5, -4, -3, 1, 3, 4, 5, 6, 7),
        -1: (-7, -6, -5, -4, -3, 2, 3, 4, 5, 6, 7),
        1: (-7, -6, -5, -4, -3, -2, 3, 4, 5, 6, 7),
        2: (-7, -6, -5, -4, -3, -1, 3, 4, 5, 6, 7),
        3: (-5, -4, -2, -1, 1, 2,),
        4: (-6, -5, -3, -2, -1, 1, 2,),
        5: (-7, -6, -4, -3, -2, -1, 1, 2,),
        6: (-7, -5, -4, -2, -1, 1, 2,),
        7: (-6, -5, -2, -1, 1, 2,),
    }

    perfectUp = (5, 7)
    perfectDown = (-7, -5)

    def __init__(self, melody):
        if melody == None:
            self.tones = [Tone(Config.midiE3)]  # [ Tone(Config.vocalRanges["bass"][1]) ]
            self.intervals = []
        else:
            self.tones = copy.deepcopy(melody.tones)
            self.intervals = copy.deepcopy(melody.intervals)

    def pushInterval(self, interval):
        self.intervals.append(interval)
        self.tones.append(Tone(self.tones[-1].midiNote + interval))

    def popInterval(self):
        self.tones.pop()
        return self.intervals.pop()

    def melodyHeight(self):
        midiTones = [x.midiNote for x in self.tones]
        maxTone = max(midiTones)
        minTone = min(midiTones)
        return maxTone - minTone

    def numTones(self):
        return len(self.tones)

    def numIntervals(self):
        return len(self.intervals)

    def numDirectionChanges(self):
        directionChanges = 0
        positive = self.intervals[0] > 0
        for interval in self.intervals:
            if positive == True and interval < 0 or \
                    positive == False and interval > 0:
                directionChanges += 1
                positive = not positive
        return directionChanges

    def hasTooLargeARange(self):
        return self.melodyHeight() > Config.maxMelodyHeight

    def hasTooManyInSameDirection(self):
        if self.numIntervals() < 5:
            return False
        direction = (self.intervals[-5] > 0)
        for interval in self.intervals[-4:]:
            if (interval > 0) != direction:
                return False
        return True

    def hasDuplicateTones(self):
        # ignore melody-final tones
        if self.tones[0].midiNote == self.tones[-1].midiNote:
            return False
        for existingTone in self.tones[1:-1]:
            if existingTone.midiNote == self.tones[-1].midiNote:
                return True
        return False

    def hasDuplicateIntervals(self):
        addedInterval = self.intervals[-1];
        for existingInterval in self.intervals[0:-2]:
            if existingInterval == addedInterval:
                return True
        return False

    def hasThreeSequencesOfTwo(self):
        # 3 repeats of same two-tone interval
        sequenceCounts = {}
        for interval in self.intervals:
            newCount = sequenceCounts.get(interval, 0) + 1
            if newCount > 2:
                return True
            sequenceCounts[interval] = newCount
        return False

    def hasTwoSequencesOfThree(self):
        length = self.numIntervals()
        if length < 4:
            return False
        # 2 repeats of longer non-overlapping sequences
        pattern = (self.intervals[-2], self.intervals[-1])
        pos = 0
        while length - pos > 2:
            intervals = (self.intervals[pos], self.intervals[pos + 1])
            if pattern == intervals:
                return True
            inverted = intervals * -1
            if pattern == inverted:
                return True
            pos += 1
        return False

    def hasUnamelioratedTritone(self):
        ints = self.numIntervals()
        if ints < 2:
            return False
        elif ints == 2:
            if self.intervals[0] == -6:
                if self.intervals[1] not in self.perfectUp:
                    return True
            elif self.intervals[0] == 6:
                if self.intervals[1] not in self.perfectDown:
                    return True
        else:
            if self.intervals[-2] == -6:
                if self.intervals[-3] not in self.perfectUp and \
                        self.intervals[-1] not in self.perfectUp:
                    return True
            elif self.intervals[-2] == 6:
                if self.intervals[-3] not in self.perfectDown and \
                        self.intervals[-1] not in self.perfectDown:
                    return True
        return False

    def hasTooManyDirectionChanges(self):
        return self.numDirectionChanges() > Config.maxDirectionChanges

    # def isComplete(self):
    #    return self.tones[0].midiNote == self.tones[-1].midiNote

    def isIllegalMelodyForHindemithChapterOne(self):
        # Some tests assume we just need to check the
        # most recently appended note

        if len(self.intervals) < 2:
            return False

        closing = (self.tones[0].midiNote == self.tones[-1].midiNote)

        if closing and len(self.intervals) < Config.minMelodyIntervals:
            return True

        if self.hasDuplicateTones() or \
                self.hasDuplicateIntervals() or \
                self.hasUnamelioratedTritone() or \
                self.hasTooLargeARange() or \
                self.hasTooManyInSameDirection() or \
                self.hasTwoSequencesOfThree() or \
                self.hasThreeSequencesOfTwo() or \
                self.hasTooManyDirectionChanges() \
                :
            return True

        if closing:
            if self.intervals[-1] not in self.possibleLastIntervals:
                return True

        return False

    def intervalsString(self):
        strings = []
        for interval in self.intervals:
            strings.append(str(interval))
        return " ".join(strings)

    def tonesString(self):
        strs = []
        for tone in self.tones:
            spelling = tone.getSpelling()  # tone.getSpellingAndOctave()
            strs.append(spelling)
        return " ".join(strs)

    def getName(self):
        return '{0}  /  {1}'.format(self.tonesString(), self.intervalsString())

    def print(self):
        strs = []
        strs.append(self.tonesString())
        strs.append(" == ")
        strs.append(self.intervalsString())
        print(self.getName())

    def playMidi(self, player, duration, pause):
        print(self.intervalsString(), " -- ", end='')

        # music21Notes = []
        for tone in self.tones:
            spelling = tone.getSpellingAndOctave()
            print(spelling, end=' ')
            # music21Notes.append(note.Note(spelling))
            player.noteOn(tone.midiNote, 127)
            time.sleep(duration)
            player.noteOff(tone.midiNote, 127)
        print()

        time.sleep(pause)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class MelodiesSubset:

    def __init__(self, numDirectionChanges, melodySize):
        self.melodySize = melodySize
        self.numDirectionChanges = numDirectionChanges
        self.melodies = {x: [] for x in Melody.possibleLastIntervals}

    def getName(self):
        return "Melodies with {0} direction changes and length {1}".format( \
            self.numDirectionChanges, self.melodySize)

    def append(self, melody):
        self.melodies[melody.intervals[-1]].append(melody)

    def numMelodies(self):
        lengths = [len(z) for z in self.melodies.values()]
        return functools.reduce(lambda x, y: x + y, lengths)

    def getAllMelodiesUpToMaxForGroup(self):
        allMelodies = []
        for lastInterval in Melody.possibleLastIntervals:
            melodies = self.melodies[lastInterval][0:Config.maxMelodiesPerFinalIntervalSubset]
            allMelodies.extend(melodies)
        return allMelodies


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class MelodySets:
    melodyCount = 0

    def __init__(self):
        self.directionChangesSet = []
        for altCount in range(0, Config.maxMelodyIntervals + 2):
            lengthSet = []
            self.directionChangesSet.append(lengthSet)
            for lengthCount in range(0, Config.maxMelodyIntervals + 2):
                lengthSet.append(MelodiesSubset(altCount, lengthCount))

    def saveMelody(self, melody):

        self.melodyCount += 1

        melody = Melody(melody)
        midiTones = [x.midiNote for x in melody.tones]
        maxTone = max(midiTones)
        minTone = min(midiTones)
        midTone = (maxTone + minTone) // 2
        offset = Config.midiE3 - midTone

        i = 0
        while i < melody.numTones():
            melody.tones[i].midiNote += offset
            i += 1

        length = melody.numTones()

        directionChanges = melody.numDirectionChanges()

        melodySet = self.directionChangesSet[directionChanges][length]
        melodySet.append(melody)

        currentTime = time.time()

        global lastUpdateTime
        if (currentTime - lastUpdateTime) > Config.progressUpdateSeconds:
            self.printSummary()
            print()
            melody.print()
            lastUpdateTime = currentTime

    def extendMelody(self, melody, lengthRemaining):

        previousInterval = melody.intervals[-1]
        for interval in Melody.possibleFollowingIntervals[previousInterval]:
            melody.pushInterval(interval)
            if not melody.isIllegalMelodyForHindemithChapterOne():
                if melody.tones[0].midiNote == melody.tones[-1].midiNote:
                    self.saveMelody(melody)
                elif lengthRemaining > 0:
                    self.extendMelody(melody, lengthRemaining - 1)

            melody.popInterval()

    def generateMelodies(self, length):
        for interval in Melody.possibleFirstIntervals:
            melody = Melody(None)
            melody.pushInterval(interval)
            self.extendMelody(melody, length - 1)
        self.shuffleIfTooMany()
        self.printSummary()

    def shuffleIfTooMany(self):
        for alternationSet in self.directionChangesSet:
            for lengthSet in alternationSet:
                for finalInterval in Melody.possibleLastIntervals:
                    melodies = lengthSet.melodies[finalInterval]
                    if len(melodies) > Config.maxMelodiesPerFinalIntervalSubset:
                        shuffle(melodies)

    # def printPrefixes(self):
    #    self.printSummary()
    #    for melodySet in self.melodies:
    #        for melody in melodySet:
    #            melody.print()

    def printSummary(self):
        print()
        totalMelodies = 0
        for i in range(0, len(self.directionChangesSet)):
            directionsSet = self.directionChangesSet[i]
            for j in range(0, len(directionsSet)):
                lengthSet = directionsSet[j]
                numMelodies = lengthSet.numMelodies()
                if numMelodies > 0:
                    print(numMelodies, " melodies of direction changes ", i, \
                          " and size ", j)
        print("Total: ", self.melodyCount)

    def setTrue(val):
        val = True

    def setFalse(val):
        val = False

    def playMelodies(self):
        self.printSummary()

        pygame.midi.init()
        player = pygame.midi.Output(0)
        player.setInstrument(0)

        allMelodies = []
        for directionsSet in self.melodies:
            for lengthSet in directionsSet:
                allMelodies.append(lengthSet.getAllMelodies())

        repeat = True

        for melody in allMelodies:
            melody.playMidi(player, 0.25, 1)
            # melody.playMidi(player, 0.325, 1.5)
            # melody.playMidi(player, 0.4, 3)

        del player
        pygame.midi.quit()

    def playOneMelody(self, melody):
        pygame.midi.init()
        player = pygame.midi.Output(0)
        player.setInstrument(0)

        melody.playMidi(player, 0.25, 2)

        del player
        pygame.midi.quit()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# approx EBNF
#
# MusicXML File Output  = <File Header>, { <Melody> }, <File Footer>
# <File Header>         = appendFileHeader()
# <File Footer>         = appendFileFooter()
# <Melody>              = [ <First Measure> | <New Melody Measure> ]
#                           { <Note Measure> }
#                           <Melody End>
# <First Measure>       = getMeasureStart()
#                           getExtraForFirstMeasure()
#                           getMelodyTitle()
#                           <Musical Note>
#                           getMeasureEnd()
# <New Melody Measure>  = getMeasureStart()
#                           getExtraForNewSystem()
#                           getMelodyTitle()
#                           <Musical Note>
#                           getMeasureEnd()
# <Note Measure>        = getMeasureStart()
#                           <Musical Note>
#                           getMeasureEnd()
# <Melody End>          = <Multirest Measure>
#                           <Rest Measure>
#                           <Rest Measure>
#                           <Ending Rest Measure>
# <Musical Note>        = getMusicalNote()
# <Multirest Measure>   = getMeasureStart()
#                           getMultiRest()
#                           getMeasureEnd()
# <Rest Measure>        = getMeasureStart()
#                           getRest()
#                           getMeasureEnd()
# <Ending Rest Measure> =   getMeasureStart()
#                           getRest()
#                           getEndBarline()
#                           getMeasureEnd()
class MusicXmlExporter:
    docWidth = 1200 - 141 - 70
    firstMeasureExtraWidth = 165 - 95
    newSystemExtraWidth = 165 - 95
    multiRestExtraWidth = 145 - 95

    def exportMelodySets(self, melodySets):
        for altCount in range(0, Config.maxMelodyIntervals + 2):
            alternationSet = melodySets.directionChangesSet[altCount]
            for lengthCount in range(0, Config.maxMelodyIntervals + 2):
                melodySet = alternationSet[lengthCount]
                self.exportMelodies(melodySet)

    def exportMelodies(self, melodySubset):
        if melodySubset.numMelodies() > 0:
            xmlDoc = []
            name = melodySubset.getName()

            self.appendFileHeader(xmlDoc, melodySubset, name)
            self.appendMelodies(xmlDoc, melodySubset)
            self.appendFileFooter(xmlDoc)

            self.writeXmlDoc(xmlDoc, name)

    def appendFileHeader(self, doc, melodies, name):
        title = 'Python-Generated Hindemith-Compliant Melodies'
        composer = 'Jodawi'
        copyrightNotice = 'Public Domain'
        subtitle = name
        software = os.path.basename(sys.argv[0])
        today = datetime.date.today().isoformat()

        header = self.fileHeader.format( \
            TITLE=title, \
            COMPOSER=composer, \
            COPYRIGHT=copyrightNotice, \
            SUBTITLE=subtitle, \
            SOFTWARE=software, \
            DATE=today, \
            )
        doc.append(header)

    def appendFileFooter(self, doc):
        doc.append(self.fileFooter)

    def appendMelodies(self, doc, melodySet):
        melodyCount = 0
        measureNumber = 0
        for melody in melodySet.getAllMelodiesUpToMaxForGroup():
            melodyCount += 1
            name = '{0}.{1}.{2}:  {3}'.format( \
                melodySet.numDirectionChanges, \
                melodySet.melodySize, \
                melodyCount, \
                melody.getName())
            measureNumber += self.appendMelody( \
                doc, melody, name, melodyCount, measureNumber)

    def getMelodyMeasureWidth(self, melody):
        shrunken = self.docWidth \
                   - self.firstMeasureExtraWidth \
                   - self.multiRestExtraWidth

        return shrunken // (melody.numTones() + 1)

    def getRestMeasureWidth(self, melody):
        return self.docWidth - self.firstMeasureExtraWidth - \
               self.getMelodyMeasureWidth(melody) * melody.numTones()

    def writeXmlDoc(self, doc, name):
        #TODO: create folder
        data_folder = Path("out/")

        fileName = data_folder / (name + '.xml')

        with open(fileName, mode='w', encoding="utf8") as f:
            for item in doc:
                f.write(item)
            print("Wrote ", fileName)

    def appendMelody(self, doc, melody, name, melodyNumber, measureNumber):

        baseWidth = self.getMelodyMeasureWidth(melody)

        for i in range(len(melody.tones)):
            width = baseWidth
            defaultX = 13
            if i == 0:
                width += self.firstMeasureExtraWidth
                defaultX += self.firstMeasureExtraWidth
            measureNumber += 1
            doc.append(self.measureStart.format( \
                MEASURE_NUMBER=measureNumber, \
                MEASURE_WIDTH=width))

            if measureNumber == 1:
                doc.append(self.extraForFirstMeasure)
            elif melodyNumber != 1 and i == 0:
                doc.append(self.newSystem)

            if i == 0:
                doc.append(self.melodyTitle.format( \
                    MELODY_TITLE=name))

            tone = melody.tones[i]
            noteStr = ''
            if tone.isSharp():
                noteStr = self.noteSharp( \
                    tone.getLetter(), \
                    tone.getOctave(), \
                    defaultX)
            else:
                noteStr = self.noteNatural( \
                    tone.getLetter(), \
                    tone.getOctave(), \
                    defaultX)
            doc.append(noteStr)

            doc.append(self.measureEnd)

        restStr = ''
        for i in range(4):
            measureNumber += 1
            width = 0
            restStr = self.rest
            if i == 0:
                width = self.getRestMeasureWidth(melody)
                restStr = self.multipleRest + self.rest

            doc.append(self.measureStart.format( \
                MEASURE_NUMBER=measureNumber, \
                MEASURE_WIDTH=width))
            doc.append(restStr)
            if i == 3:
                doc.append(self.endBarline)
            doc.append(self.measureEnd)

        return measureNumber

    measure = '''\
{MEASURE_START_WITH_APPROPRIATE_WIDTH}\
{EXTRA_FOR_FIRST_MEASURE}\
{EXTRA_FOR_NEW_SYSTEM}\
{EXTRA_FOR_MELODY_TITLE}\
{EXTRA_FOR_MUSICAL_NOTE}\
{EXTRA_FOR_MULTIPLE_REST}\
{EXTRA_FOR_REST}\
{EXTRA_FOR_END_BARLINE}\
{MEASURE_END}'''

    fileHeader = '''\
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.0 \
Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.0">
  <movement-title>{TITLE}</movement-title>
  <identification>
    <creator type="composer">{COMPOSER}</creator>
    <rights>©{COPYRIGHT}</rights>
    <encoding>
      <software>{SOFTWARE}</software>
      <software>Dolet Light for Finale 2012</software>
      <encoding-date>{DATE}</encoding-date>
      <supports attribute="new-system" element="print" type="yes" value="yes"/>
      <supports attribute="new-page" element="print" type="yes" value="yes"/>
    </encoding>
  </identification>
  <defaults>
    <scaling>
      <millimeters>7.1967</millimeters>
      <tenths>40</tenths>
    </scaling>
    <page-layout>
      <page-height>1553</page-height>
      <page-width>1200</page-width>
      <page-margins type="both">
        <left-margin>141</left-margin>
        <right-margin>70</right-margin>
        <top-margin>70</top-margin>
        <bottom-margin>70</bottom-margin>
      </page-margins>
    </page-layout>
    <system-layout>
      <system-margins>
        <left-margin>0</left-margin>
        <right-margin>0</right-margin>
      </system-margins>
      <system-distance>84</system-distance>
      <top-system-distance>49</top-system-distance>
    </system-layout>
    <appearance>
      <line-width type="stem">0.7487</line-width>
      <line-width type="beam">5</line-width>
      <line-width type="staff">0.7487</line-width>
      <line-width type="light barline">0.7487</line-width>
      <line-width type="heavy barline">5</line-width>
      <line-width type="leger">0.7487</line-width>
      <line-width type="ending">0.7487</line-width>
      <line-width type="wedge">0.7487</line-width>
      <line-width type="enclosure">0.7487</line-width>
      <line-width type="tuplet bracket">0.7487</line-width>
      <note-size type="grace">60</note-size>
      <note-size type="cue">60</note-size>
      <distance type="hyphen">120</distance>
      <distance type="beam">8</distance>
    </appearance>
    <music-font font-family="Maestro,engraved" font-size="20.4"/>
    <word-font font-family="Times New Roman" font-size="10.2"/>
  </defaults>
  <credit page="1">
    <credit-type>title</credit-type>
    <credit-words default-x="635" default-y="1482" font-size="24" \
justify="center" valign="top">{TITLE}</credit-words>
  </credit>
  <credit page="1">
    <credit-type>composer</credit-type>
    <credit-words default-x="1127" default-y="1414" font-size="12" \
justify="right" valign="top">{COMPOSER}</credit-words>
  </credit>
  <credit page="1">
    <credit-type>rights</credit-type>
    <credit-words default-x="635" default-y="53" font-size="10" \
justify="center" valign="bottom">©{COPYRIGHT}</credit-words>
  </credit>
  <credit page="1">
    <credit-type>subtitle</credit-type>
    <credit-words default-x="635" default-y="1418" font-size="18" \
justify="center" valign="top">{SUBTITLE}</credit-words>
  </credit>
  <part-list>
    <score-part id="P1">
      <part-name>Bass</part-name>
      <part-abbreviation>B</part-abbreviation>
      <score-instrument id="P1-I1">
        <instrument-name>ARIA Player</instrument-name>
        <virtual-instrument>
          <virtual-library>Garritan Instruments for Finale</virtual-library>
          <virtual-name>009. Choir/Choir Ahs</virtual-name>
        </virtual-instrument>
      </score-instrument>
      <midi-device>ARIA Player</midi-device>
      <midi-instrument id="P1-I1">
        <midi-channel>1</midi-channel>
        <midi-program>1</midi-program>
        <volume>80</volume>
        <pan>0</pan>
      </midi-instrument>
    </score-part>
  </part-list>
  <!--=========================================================-->
  <part id="P1">'''

    measureStart = '''
    <measure number="{MEASURE_NUMBER}" width="{MEASURE_WIDTH}">'''

    extraForFirstMeasure = '''
      <print>
        <system-layout>
          <top-system-distance>174</top-system-distance>
        </system-layout>
        <measure-numbering>system</measure-numbering>
      </print>
      <attributes>
        <divisions>2</divisions>
        <key>
          <fifths>0</fifths>
          <mode>major</mode>
        </key>
        <time>
          <beats>1</beats>
          <beat-type>1</beat-type>
        </time>
        <clef>
          <sign>F</sign>
          <line>4</line>
        </clef>
      </attributes>
      <sound tempo="640"/>'''

    melodyTitle = '''
      <direction placement="above">
        <direction-type>
          <words default-y="38" relative-x="-10" \
valign="top">{MELODY_TITLE}</words>
        </direction-type>
      </direction>'''

    optionalAlter = '''\
          <alter>{ALTER}</alter>
'''

    optionalAccidental = '''\
        <accidental>{ACCIDENTAL}</accidental>
'''

    def noteSharp(self, step, octave, defaultX):
        alter = self.optionalAlter.format( \
            ALTER=1)
        accidental = self.optionalAccidental.format( \
            ACCIDENTAL="sharp")
        return self.note(step, octave, alter, accidental, defaultX)

    def noteNatural(self, step, octave, defaultX):
        return self.note(step, octave, '', '', defaultX)

    def note(self, step, octave, alter, accidental, defaultX):
        return self.musicalNote.format( \
            STEP=step, \
            OCTAVE=octave, \
            NOTE_DEFAULT_X=defaultX, \
            OPTIONAL_ALTER=alter, \
            OPTIONAL_ACCIDENTAL=accidental)

    musicalNote = '''
      <note default-x="{NOTE_DEFAULT_X}">
        <pitch>
          <step>{STEP}</step>
{OPTIONAL_ALTER}\
          <octave>{OCTAVE}</octave>
        </pitch>
        <duration>8</duration>
        <voice>1</voice>
        <type>whole</type>
{OPTIONAL_ACCIDENTAL}\
      </note>'''

    measureEnd = '''
    </measure>
    <!--=======================================================-->'''

    multipleRest = '''
      <attributes>
        <measure-style>
          <multiple-rest>4</multiple-rest>
        </measure-style>
      </attributes>'''

    # with zero width for the final 3
    rest = '''
      <note>
        <rest measure="yes"/>
        <duration>8</duration>
        <voice>1</voice>
      </note>'''

    endBarline = '''
      <barline location="right">
        <bar-style>light-heavy</bar-style>
      </barline>'''

    newSystem = '''
      <print new-system="yes">
        <system-layout>
          <system-distance>79</system-distance>
        </system-layout>
      </print>'''

    fileFooter = '''
  </part>
  <!--=========================================================-->
</score-partwise>
'''


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def main():
    melodySets = MelodySets()
    melodySets.generateMelodies(Config.maxMelodyIntervals)

    exporter = MusicXmlExporter()
    exporter.exportMelodySets(melodySets)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# if __name__ == '__main__':
#    unittest.main()

main()

import copy
import datetime
import functools
import os
import sys
import time
from pathlib import Path
from random import shuffle

import pygame.midi

# import cProfile
# from music21 import *

last_update_time = time.time()


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class Config:
    progress_update_seconds = 5
    last_update_time = 0

    max_melodies_per_final_interval_subset = 100

    min_melody_intervals = 4
    max_melody_intervals = 14
    max_melody_height = 19
    max_direction_changes = 14

    midi_a0 = 21
    midi_e3 = 52
    midi_c4 = 60
    midi_c8 = 108

    vocal_ranges = {
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

    def __init__(self, midi_note):
        self.midi_note = midi_note

    note_to_spelling = {
        0: "A", 1: "A♯", 2: "B", 3: "C", 4: "C♯", 5: "D",
        6: "D♯", 7: "E", 8: "F", 9: "F♯", 10: "G", 11: "G♯"}

    spelling_to_note = {
        "A": 0, "A♯": 1, "B♭": 1, "B": 2, "C♭": 2, "B♯": 3,
        "C": 3, "C♯": 4, "D♭": 4, "D": 5, "D♯": 6, "E♭": 6,
        "E": 7, "F♭": 7, "E♯": 8, "F": 8, "F♯": 9, "G♭": 9,
        "G": 10, "G♯": 11, "A♭": 11}

    def get_note_number(self): return self.midi_note - Config.midi_a0

    def get_octave(self): return (self.get_note_number() + 12 - 3) // 12

    def get_spelling(self): return self.note_to_spelling[self.get_note_number() % 12]

    def is_sharp(self): return self.get_spelling()[-1] == '♯'

    def get_letter(self): return self.get_spelling()[0]

    def get_spelling_and_octave(self):
        note = self.get_note_number()
        name = self.note_to_spelling[note % 12]
        return name + str(self.get_octave())


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class Melody:
    possible_first_intervals = \
        (-7, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 7)

    possible_last_intervals = \
        (-7, -4, -3, -2, -1, 1, 2, 5,)

    possible_following_intervals = {
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

    perfect_up = (5, 7)
    perfect_down = (-7, -5)

    def __init__(self, melody):
        if melody is None:
            self.tones = [Tone(Config.midi_e3)]  # [ Tone(Config.vocalRanges["bass"][1]) ]
            self.intervals = []
        else:
            self.tones = copy.deepcopy(melody.tones)
            self.intervals = copy.deepcopy(melody.intervals)

    def push_interval(self, interval):
        self.intervals.append(interval)
        self.tones.append(Tone(self.tones[-1].midi_note + interval))

    def pop_interval(self):
        self.tones.pop()
        return self.intervals.pop()

    def melody_height(self):
        midi_tones = [x.midi_note for x in self.tones]
        max_tone = max(midi_tones)
        min_tone = min(midi_tones)
        return max_tone - min_tone

    def num_tones(self):
        return len(self.tones)

    def num_intervals(self):
        return len(self.intervals)

    def num_direction_changes(self):
        direction_changes = 0
        positive = self.intervals[0] > 0
        for interval in self.intervals:
            if positive is True and interval < 0 or \
                    positive is False and interval > 0:
                direction_changes += 1
                positive = not positive
        return direction_changes

    def has_too_large_a_range(self):
        return self.melody_height() > Config.max_melody_height

    def has_too_many_in_same_direction(self):
        if self.num_intervals() < 5:
            return False
        direction = (self.intervals[-5] > 0)
        for interval in self.intervals[-4:]:
            if (interval > 0) != direction:
                return False
        return True

    def has_duplicate_tones(self):
        # ignore melody-final tones
        if self.tones[0].midi_note == self.tones[-1].midi_note:
            return False
        for existing_tone in self.tones[1:-1]:
            if existing_tone.midi_note == self.tones[-1].midi_note:
                return True
        return False

    def has_duplicate_intervals(self):
        added_interval = self.intervals[-1]
        for existing_interval in self.intervals[0:-2]:
            if existing_interval == added_interval:
                return True
        return False

    def has_three_sequences_of_two(self):
        # 3 repeats of same two-tone interval
        sequence_counts = {}
        for interval in self.intervals:
            new_count = sequence_counts.get(interval, 0) + 1
            if new_count > 2:
                return True
            sequence_counts[interval] = new_count
        return False

    def has_two_sequences_of_three(self):
        length = self.num_intervals()
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

    def has_unameliorated_tritone(self):
        ints = self.num_intervals()
        if ints < 2:
            return False
        elif ints == 2:
            if self.intervals[0] == -6:
                if self.intervals[1] not in self.perfect_up:
                    return True
            elif self.intervals[0] == 6:
                if self.intervals[1] not in self.perfect_down:
                    return True
        else:
            if self.intervals[-2] == -6:
                if self.intervals[-3] not in self.perfect_up and \
                        self.intervals[-1] not in self.perfect_up:
                    return True
            elif self.intervals[-2] == 6:
                if self.intervals[-3] not in self.perfect_down and \
                        self.intervals[-1] not in self.perfect_down:
                    return True
        return False

    def has_too_many_direction_changes(self):
        return self.num_direction_changes() > Config.max_direction_changes

    # def isComplete(self):
    #    return self.tones[0].midi_note == self.tones[-1].midi_note

    def is_illegal_melody_for_hindemith_chapter_one(self):
        # Some tests assume we just need to check the
        # most recently appended note

        if len(self.intervals) < 2:
            return False

        closing = (self.tones[0].midi_note == self.tones[-1].midi_note)

        if closing and len(self.intervals) < Config.min_melody_intervals:
            return True

        if (self.has_duplicate_tones() or
                self.has_duplicate_intervals() or
                self.has_unameliorated_tritone() or
                self.has_too_large_a_range() or
                self.has_too_many_in_same_direction() or
                self.has_two_sequences_of_three() or
                self.has_three_sequences_of_two() or
                self.has_too_many_direction_changes()
        ):
            return True

        if closing:
            if self.intervals[-1] not in self.possible_last_intervals:
                return True

        return False

    def intervals_string(self):
        strings = []
        for interval in self.intervals:
            strings.append(str(interval))
        return " ".join(strings)

    def tones_string(self):
        strs = []
        for tone in self.tones:
            spelling = tone.get_spelling()  # tone.getSpellingAndOctave()
            strs.append(spelling)
        return " ".join(strs)

    def get_name(self):
        return '{0}  /  {1}'.format(self.tones_string(), self.intervals_string())

    def print(self):
        print(self.get_name())

    def play_midi(self, player, duration, pause):
        print(self.intervals_string(), " -- ", end='')

        # music21Notes = []
        for tone in self.tones:
            spelling = tone.get_spelling_and_octave()
            print(spelling, end=' ')
            # music21Notes.append(note.Note(spelling))
            player.noteOn(tone.midi_note, 127)
            time.sleep(duration)
            player.noteOff(tone.midi_note, 127)
        print()

        time.sleep(pause)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class MelodiesSubset:

    def __init__(self, num_direction_changes, melody_size):
        self.melody_size = melody_size
        self.num_direction_changes = num_direction_changes
        self.melodies = {x: [] for x in Melody.possible_last_intervals}

    def get_name(self):
        return "Melodies with {0} direction changes and length {1}".format(
            self.num_direction_changes, self.melody_size)

    def append(self, melody):
        self.melodies[melody.intervals[-1]].append(melody)

    def num_melodies(self):
        lengths = [len(z) for z in self.melodies.values()]
        return functools.reduce(lambda x, y: x + y, lengths)

    def get_all_melodies_up_to_max_for_group(self):
        all_melodies = []
        for last_interval in Melody.possible_last_intervals:
            melodies = self.melodies[last_interval][0:Config.max_melodies_per_final_interval_subset]
            all_melodies.extend(melodies)
        return all_melodies


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
class MelodySets:
    melody_count = 0

    def __init__(self):
        self.direction_changes_set = []
        for alt_count in range(0, Config.max_melody_intervals + 2):
            length_set = []
            self.direction_changes_set.append(length_set)
            for length_count in range(0, Config.max_melody_intervals + 2):
                length_set.append(MelodiesSubset(alt_count, length_count))

    def save_melody(self, melody):

        self.melody_count += 1

        melody = Melody(melody)
        midi_tones = [x.midi_note for x in melody.tones]
        max_tone = max(midi_tones)
        min_tone = min(midi_tones)
        mid_tone = (max_tone + min_tone) // 2
        offset = Config.midi_e3 - mid_tone

        i = 0
        while i < melody.num_tones():
            melody.tones[i].midi_note += offset
            i += 1

        length = melody.num_tones()

        direction_changes = melody.num_direction_changes()

        melody_set = self.direction_changes_set[direction_changes][length]
        melody_set.append(melody)

        current_time = time.time()

        global last_update_time
        if (current_time - last_update_time) > Config.progress_update_seconds:
            self.print_summary()
            print()
            melody.print()
            last_update_time = current_time

    def extend_melody(self, melody, length_remaining):

        previous_interval = melody.intervals[-1]
        for interval in Melody.possible_following_intervals[previous_interval]:
            melody.push_interval(interval)
            if not melody.is_illegal_melody_for_hindemith_chapter_one():
                if melody.tones[0].midi_note == melody.tones[-1].midi_note:
                    self.save_melody(melody)
                elif length_remaining > 0:
                    self.extend_melody(melody, length_remaining - 1)

            melody.pop_interval()

    def generate_melodies(self, length):
        for interval in Melody.possible_first_intervals:
            melody = Melody(None)
            melody.push_interval(interval)
            self.extend_melody(melody, length - 1)
        self.shuffle_if_too_many()
        self.print_summary()

    def shuffle_if_too_many(self):
        for alternation_set in self.direction_changes_set:
            for length_set in alternation_set:
                for final_interval in Melody.possible_last_intervals:
                    melodies = length_set.melodies[final_interval]
                    if len(melodies) > Config.max_melodies_per_final_interval_subset:
                        shuffle(melodies)

    # def print_prefixes(self):
    #    self.print_summary()
    #    for melody_set in self.melodies:
    #        for melody in melody_set:
    #            melody.print()

    def print_summary(self):
        print()
        for i in range(0, len(self.direction_changes_set)):
            directions_set = self.direction_changes_set[i]
            for j in range(0, len(directions_set)):
                length_set = directions_set[j]
                num_melodies = length_set.num_melodies()
                if num_melodies > 0:
                    print(num_melodies, " melodies of direction changes ", i, " and size ", j)
        print("Total: ", self.melody_count)

    def play_melodies(self):
        self.print_summary()

        pygame.midi.init()
        player = pygame.midi.Output(0)
        player.setInstrument(0)

        all_melodies = []
        for directions_set in self.melodies:
            for length_set in directions_set:
                all_melodies.append(length_set.get_all__melodies())

        for melody in all_melodies:
            melody.play_midi(player, 0.25, 1)
            # melody.playMidi(player, 0.325, 1.5)
            # melody.playMidi(player, 0.4, 3)

        del player
        pygame.midi.quit()

    def play_one_melody(self, melody):
        pygame.midi.init()
        player = pygame.midi.Output(0)
        player.setInstrument(0)

        melody.play_midi(player, 0.25, 2)

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
    doc_width = 1200 - 141 - 70
    first_measure_extra_width = 165 - 95
    new_system_extra_width = 165 - 95
    multi_rest_extra_width = 145 - 95

    def export_melody_sets(self, melody_sets):
        for alt_count in range(0, Config.max_melody_intervals + 2):
            alternation_set = melody_sets.direction_changes_set[alt_count]
            for length_count in range(0, Config.max_melody_intervals + 2):
                melody_set = alternation_set[length_count]
                self.export_melodies(melody_set)

    def export_melodies(self, melody_subset):
        if melody_subset.num_melodies() > 0:
            xml_doc = []
            name = melody_subset.get_name()

            self.append_file_header(xml_doc, name)
            self.append_melodies(xml_doc, melody_subset)
            self.append_file_footer(xml_doc)

            self.write_xml_doc(xml_doc, name)

    def append_file_header(self, doc, name):
        title = 'Python-Generated Hindemith-Compliant Melodies'
        composer = 'Jodawi'
        copyright_notice = 'Public Domain'
        subtitle = name
        software = os.path.basename(sys.argv[0])
        today = datetime.date.today().isoformat()

        header = self.file_header.format(
            TITLE=title,
            COMPOSER=composer,
            COPYRIGHT=copyright_notice,
            SUBTITLE=subtitle,
            SOFTWARE=software,
            DATE=today,
        )
        doc.append(header)

    def append_file_footer(self, doc):
        doc.append(self.file_footer)

    def append_melodies(self, doc, melody_set):
        melody_count = 0
        measure_number = 0
        for melody in melody_set.get_all_melodies_up_to_max_for_group():
            melody_count += 1
            name = '{0}.{1}.{2}:  {3}'.format(
                melody_set.num_direction_changes,
                melody_set.melody_size,
                melody_count,
                melody.get_name())
            measure_number += self.append_melody(doc, melody, name, melody_count, measure_number)

    def get_melody_measure_width(self, melody):
        shrunken = self.doc_width \
                   - self.first_measure_extra_width \
                   - self.multi_rest_extra_width

        return shrunken // (melody.num_tones() + 1)

    def get_rest_measure_width(self, melody):
        return self.doc_width - self.first_measure_extra_width - \
               self.get_melody_measure_width(melody) * melody.num_tones()

    def write_xml_doc(self, doc, name):
        # TODO: create folder
        data_folder = Path("out/")

        file_name = data_folder / (name + '.xml')

        with open(file_name, mode='w', encoding="utf8") as f:
            for item in doc:
                f.write(item)
            print("Wrote ", file_name)

    def append_melody(self, doc, melody, name, melody_number, measure_number):

        base_width = self.get_melody_measure_width(melody)

        for i in range(len(melody.tones)):
            width = base_width
            default_x = 13
            if i == 0:
                width += self.first_measure_extra_width
                default_x += self.first_measure_extra_width
            measure_number += 1
            doc.append(self.measure_start.format(
                MEASURE_NUMBER=measure_number,
                MEASURE_WIDTH=width))

            if measure_number == 1:
                doc.append(self.extra_for_first_measure)
            elif melody_number != 1 and i == 0:
                doc.append(self.new_system)

            if i == 0:
                doc.append(self.melody_title.format(MELODY_TITLE=name))

            tone = melody.tones[i]
            if tone.is_sharp():
                note_str = self.note_sharp(
                    tone.get_letter(),
                    tone.get_octave(),
                    default_x)
            else:
                note_str = self.note_natural(
                    tone.get_letter(),
                    tone.get_octave(),
                    default_x)
            doc.append(note_str)

            doc.append(self.measure_end)

        for i in range(4):
            measure_number += 1
            width = 0
            rest_str = self.rest
            if i == 0:
                width = self.get_rest_measure_width(melody)
                rest_str = self.multiple_rest + self.rest

            doc.append(self.measure_start.format(
                MEASURE_NUMBER=measure_number,
                MEASURE_WIDTH=width))
            doc.append(rest_str)
            if i == 3:
                doc.append(self.end_barline)
            doc.append(self.measure_end)

        return measure_number

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

    file_header = '''\
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

    measure_start = '''
    <measure number="{MEASURE_NUMBER}" width="{MEASURE_WIDTH}">'''

    extra_for_first_measure = '''
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

    melody_title = '''
      <direction placement="above">
        <direction-type>
          <words default-y="38" relative-x="-10" \
valign="top">{MELODY_TITLE}</words>
        </direction-type>
      </direction>'''

    optional_alter = '''\
          <alter>{ALTER}</alter>
'''

    optional_accidental = '''\
        <accidental>{ACCIDENTAL}</accidental>
'''

    def note_sharp(self, step, octave, default_x):
        alter = self.optional_alter.format(ALTER=1)
        accidental = self.optional_accidental.format(ACCIDENTAL="sharp")
        return self.note(step, octave, alter, accidental, default_x)

    def note_natural(self, step, octave, default_x):
        return self.note(step, octave, '', '', default_x)

    def note(self, step, octave, alter, accidental, default_x):
        return self.musical_note.format(
            STEP=step,
            OCTAVE=octave,
            NOTE_DEFAULT_X=default_x,
            OPTIONAL_ALTER=alter,
            OPTIONAL_ACCIDENTAL=accidental)

    musical_note = '''
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

    measure_end = '''
    </measure>
    <!--=======================================================-->'''

    multiple_rest = '''
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

    end_barline = '''
      <barline location="right">
        <bar-style>light-heavy</bar-style>
      </barline>'''

    new_system = '''
      <print new-system="yes">
        <system-layout>
          <system-distance>79</system-distance>
        </system-layout>
      </print>'''

    file_footer = '''
  </part>
  <!--=========================================================-->
</score-partwise>
'''


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
def main():
    melody_sets = MelodySets()
    melody_sets.generate_melodies(Config.max_melody_intervals)

    exporter = MusicXmlExporter()
    exporter.export_melody_sets(melody_sets)


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# if __name__ == '__main__':
#    unittest.main()

main()

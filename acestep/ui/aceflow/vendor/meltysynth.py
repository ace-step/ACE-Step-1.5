import io
import itertools
import math

from array import array
from collections.abc import MutableSequence, Sequence
from enum import IntEnum
from io import BufferedIOBase
from typing import Optional


def create_buffer(length: int) -> MutableSequence[float]:
    return array("d", itertools.repeat(0, length))


class _BinaryReaderEx:
    @staticmethod
    def read_int32(reader: BufferedIOBase) -> int:
        return int.from_bytes(reader.read(4), byteorder="little", signed=True)

    @staticmethod
    def read_uint32(reader: BufferedIOBase) -> int:
        return int.from_bytes(reader.read(4), byteorder="little", signed=False)

    @staticmethod
    def read_int16(reader: BufferedIOBase) -> int:
        return int.from_bytes(reader.read(2), byteorder="little", signed=True)

    @staticmethod
    def read_uint16(reader: BufferedIOBase) -> int:
        return int.from_bytes(reader.read(2), byteorder="little", signed=False)

    @staticmethod
    def read_int8(reader: BufferedIOBase) -> int:
        return int.from_bytes(reader.read(1), byteorder="little", signed=True)

    @staticmethod
    def read_uint8(reader: BufferedIOBase) -> int:
        return int.from_bytes(reader.read(1), byteorder="little", signed=False)

    @staticmethod
    def read_int32_big_endian(reader: BufferedIOBase) -> int:
        return int.from_bytes(reader.read(4), byteorder="big", signed=True)

    @staticmethod
    def read_int16_big_endian(reader: BufferedIOBase) -> int:
        return int.from_bytes(reader.read(2), byteorder="big", signed=True)

    @staticmethod
    def read_int_variable_length(reader: BufferedIOBase) -> int:
        acc = 0
        count = 0

        while True:
            value = _BinaryReaderEx.read_uint8(reader)
            acc = (acc << 7) | (value & 127)
            if (value & 128) == 0:
                break
            count += 1
            if count == 4:
                raise Exception(
                    "The length of the value must be equal to or less than 4."
                )

        return acc

    @staticmethod
    def read_four_cc(reader: BufferedIOBase) -> str:
        data = bytearray(reader.read(4))

        for i, value in enumerate(data):
            if not (32 <= value and value <= 126):
                data[i] = 63  # '?'

        return data.decode("ascii")

    @staticmethod
    def read_fixed_length_string(reader: BufferedIOBase, length: int) -> str:
        data = reader.read(length)

        actualLength = 0
        for value in data:
            if value == 0:
                break
            actualLength += 1

        return data[0:actualLength].decode("ascii")

    @staticmethod
    def read_int16_array_as_float_array(
        reader: BufferedIOBase, size: int
    ) -> Sequence[float]:
        count = int(size / 2)
        data = array("h")
        data.fromfile(reader, count)

        return array("f", map(lambda x: x / 32768.0, data))


class _SoundFontMath:
    @staticmethod
    def half_pi() -> float:
        return math.pi / 2

    @staticmethod
    def non_audible() -> float:
        return 1.0e-3

    @staticmethod
    def log_non_audible() -> float:
        return math.log(1.0e-3)

    @staticmethod
    def timecents_to_seconds(x: float) -> float:
        return math.pow(2.0, (1.0 / 1200.0) * x)

    @staticmethod
    def cents_to_hertz(x: float) -> float:
        return 8.176 * math.pow(2.0, (1.0 / 1200.0) * x)

    @staticmethod
    def cents_to_multiplying_factor(x: float) -> float:
        return math.pow(2.0, (1.0 / 1200.0) * x)

    @staticmethod
    def decibels_to_linear(x: float) -> float:
        return math.pow(10.0, 0.05 * x)

    @staticmethod
    def linear_to_decibels(x: float) -> float:
        return 20.0 * math.log10(x)

    @staticmethod
    def key_number_to_multiplying_factor(cents: int, key: int) -> float:
        return _SoundFontMath.timecents_to_seconds(cents * (60 - key))

    @staticmethod
    def exp_cutoff(x: float) -> float:
        if x < _SoundFontMath.log_non_audible():
            return 0.0
        else:
            return math.exp(x)

    @staticmethod
    def clamp(value: float, min: float, max: float) -> float:
        if value < min:
            return min
        elif value > max:
            return max
        else:
            return value


class _ArrayMath:
    @staticmethod
    def multiply_add(
        a: float, x: Sequence[float], destination: MutableSequence[float]
    ) -> None:
        for i in range(len(destination)):
            destination[i] += a * x[i]

    @staticmethod
    def multiply_add_slope(
        a: float, step: float, x: Sequence[float], destination: MutableSequence[float]
    ) -> None:
        for i in range(len(destination)):
            destination[i] += a * x[i]
            a += step


class SoundFontVersion:
    _major: int
    _minor: int

    def __init__(self, major: int, minor: int) -> None:
        self._major = major
        self._minor = minor

    @property
    def major(self) -> int:
        return self._major

    @property
    def minor(self) -> int:
        return self._minor


class SoundFontInfo:
    _version: SoundFontVersion = SoundFontVersion(0, 0)
    _target_sound_engine: str = ""
    _bank_name: str = ""
    _rom_name: str = ""
    _rom_version: SoundFontVersion = SoundFontVersion(0, 0)
    _creation_date: str = ""
    _author: str = ""
    _target_product: str = ""
    _copyright: str = ""
    _comments: str = ""
    _tools: str = ""

    def __init__(self, reader: BufferedIOBase) -> None:
        chunk_id = _BinaryReaderEx.read_four_cc(reader)
        if chunk_id != "LIST":
            raise Exception("The LIST chunk was not found.")

        end = _BinaryReaderEx.read_uint32(reader)
        end += reader.tell()

        list_type = _BinaryReaderEx.read_four_cc(reader)
        if list_type != "INFO":
            raise Exception(
                "The type of the LIST chunk must be 'INFO', but was '"
                + list_type
                + "'."
            )

        while reader.tell() < end:
            id = _BinaryReaderEx.read_four_cc(reader)
            size = _BinaryReaderEx.read_uint32(reader)

            match id:
                case "ifil":
                    self._version = SoundFontVersion(
                        _BinaryReaderEx.read_uint16(reader),
                        _BinaryReaderEx.read_uint16(reader),
                    )

                case "isng":
                    self._target_sound_engine = (
                        _BinaryReaderEx.read_fixed_length_string(reader, size)
                    )

                case "INAM":
                    self._bank_name = _BinaryReaderEx.read_fixed_length_string(
                        reader, size
                    )

                case "irom":
                    self._rom_name = _BinaryReaderEx.read_fixed_length_string(
                        reader, size
                    )

                case "iver":
                    self._rom_version = SoundFontVersion(
                        _BinaryReaderEx.read_uint16(reader),
                        _BinaryReaderEx.read_uint16(reader),
                    )

                case "ICRD":
                    self._creation_date = _BinaryReaderEx.read_fixed_length_string(
                        reader, size
                    )

                case "IENG":
                    self._author = _BinaryReaderEx.read_fixed_length_string(
                        reader, size
                    )

                case "IPRD":
                    self._target_product = _BinaryReaderEx.read_fixed_length_string(
                        reader, size
                    )

                case "ICOP":
                    self._copyright = _BinaryReaderEx.read_fixed_length_string(
                        reader, size
                    )

                case "ICMT":
                    self._comments = _BinaryReaderEx.read_fixed_length_string(
                        reader, size
                    )

                case "ISFT":
                    self._tools = _BinaryReaderEx.read_fixed_length_string(reader, size)

                case _:
                    raise Exception(
                        "The INFO list contains an unknown ID '" + id + "'."
                    )

    @property
    def version(self) -> SoundFontVersion:
        return self._version

    @property
    def target_sound_engine(self) -> str:
        return self._target_sound_engine

    @property
    def bank_name(self) -> str:
        return self._bank_name

    @property
    def rom_name(self) -> str:
        return self._rom_name

    @property
    def rom_version(self) -> SoundFontVersion:
        return self._rom_version

    @property
    def creation_date(self) -> str:
        return self._creation_date

    @property
    def author(self) -> str:
        return self._author

    @property
    def target_product(self) -> str:
        return self._target_product

    @property
    def copyright(self) -> str:
        return self._copyright

    @property
    def comments(self) -> str:
        return self._comments

    @property
    def tools(self) -> str:
        return self._tools


class _SoundFontSampleData:
    _bits_per_sample: int
    _samples: Sequence[float]

    def __init__(self, reader: BufferedIOBase) -> None:
        chunk_id = _BinaryReaderEx.read_four_cc(reader)
        if chunk_id != "LIST":
            raise Exception("The LIST chunk was not found.")

        end = _BinaryReaderEx.read_uint32(reader)
        end += reader.tell()

        list_type = _BinaryReaderEx.read_four_cc(reader)
        if list_type != "sdta":
            raise Exception(
                "The type of the LIST chunk must be 'sdta', but was '"
                + list_type
                + "'."
            )

        bits_per_sample: int = 0
        samples: Optional[Sequence[float]] = None

        while reader.tell() < end:
            id = _BinaryReaderEx.read_four_cc(reader)
            size = _BinaryReaderEx.read_uint32(reader)

            match id:
                case "smpl":
                    bits_per_sample = 16
                    samples = _BinaryReaderEx.read_int16_array_as_float_array(
                        reader, size
                    )

                case "sm24":
                    reader.seek(size, io.SEEK_CUR)

                case _:
                    raise Exception(
                        "The INFO list contains an unknown ID '" + id + "'."
                    )

        if samples is None:
            raise Exception("No valid sample data was found.")

        self._bits_per_sample = bits_per_sample
        self._samples = samples

    @property
    def bits_per_sample(self) -> int:
        return self._bits_per_sample

    @property
    def samples(self) -> Sequence[float]:
        return self._samples


class _GeneratorType(IntEnum):
    START_ADDRESS_OFFSET = 0
    END_ADDRESS_OFFSET = 1
    START_LOOP_ADDRESS_OFFSET = 2
    END_LOOP_ADDRESS_OFFSET = 3
    START_ADDRESS_COARSE_OFFSET = 4
    MODULATION_LFO_TO_PITCH = 5
    VIBRATO_LFO_TO_PITCH = 6
    MODULATION_ENVELOPE_TO_PITCH = 7
    INITIAL_FILTER_CUTOFF_FREQUENCY = 8
    INITIAL_FILTER_Q = 9
    MODULATION_LFO_TO_FILTER_CUTOFF_FREQUENCY = 10
    MODULATION_ENVELOPE_TO_FILTER_CUTOFF_FREQUENCY = 11
    END_ADDRESS_COARSE_OFFSET = 12
    MODULATION_LFO_TO_VOLUME = 13
    UNUSED_1 = 14
    CHORUS_EFFECTS_SEND = 15
    REVERB_EFFECTS_SEND = 16
    PAN = 17
    UNUSED_2 = 18
    UNUSED_3 = 19
    UNUSED_4 = 20
    DELAY_MODULATION_LFO = 21
    FREQUENCY_MODULATION_LFO = 22
    DELAY_VIBRATO_LFO = 23
    FREQUENCY_VIBRATO_LFO = 24
    DELAY_MODULATION_ENVELOPE = 25
    ATTACK_MODULATION_ENVELOPE = 26
    HOLD_MODULATION_ENVELOPE = 27
    DECAY_MODULATION_ENVELOPE = 28
    SUSTAIN_MODULATION_ENVELOPE = 29
    RELEASE_MODULATION_ENVELOPE = 30
    KEY_NUMBER_TO_MODULATION_ENVELOPE_HOLD = 31
    KEY_NUMBER_TO_MODULATION_ENVELOPE_DECAY = 32
    DELAY_VOLUME_ENVELOPE = 33
    ATTACK_VOLUME_ENVELOPE = 34
    HOLD_VOLUME_ENVELOPE = 35
    DECAY_VOLUME_ENVELOPE = 36
    SUSTAIN_VOLUME_ENVELOPE = 37
    RELEASE_VOLUME_ENVELOPE = 38
    KEY_NUMBER_TO_VOLUME_ENVELOPE_HOLD = 39
    KEY_NUMBER_TO_VOLUME_ENVELOPE_DECAY = 40
    INSTRUMENT = 41
    RESERVED_1 = 42
    KEY_RANGE = 43
    VELOCITY_RANGE = 44
    START_LOOP_ADDRESS_COARSE_OFFSET = 45
    KEY_NUMBER = 46
    VELOCITY = 47
    INITIAL_ATTENUATION = 48
    RESERVED_2 = 49
    END_LOOP_ADDRESS_COARSE_OFFSET = 50
    COARSE_TUNE = 51
    FINE_TUNE = 52
    SAMPLE_ID = 53
    SAMPLE_MODES = 54
    RESERVED_3 = 55
    SCALE_TUNING = 56
    EXCLUSIVE_CLASS = 57
    OVERRIDING_ROOT_KEY = 58
    UNUSED_5 = 59
    UNUSED_END = 60


class _Generator:
    _generator_type: _GeneratorType
    _value: int

    def __init__(self, reader: BufferedIOBase) -> None:
        self._generator_type = _GeneratorType(_BinaryReaderEx.read_uint16(reader))
        self._value = _BinaryReaderEx.read_int16(reader)

    @staticmethod
    def read_from_chunk(reader: BufferedIOBase, size: int) -> Sequence["_Generator"]:
        if int(size % 4) != 0:
            raise Exception("The generator list is invalid.")

        count = int(size / 4) - 1
        generators = list[_Generator]()

        for _ in range(count):
            generators.append(_Generator(reader))

        # The last one is the terminator.
        _Generator(reader)

        return generators

    @property
    def generator_type(self) -> _GeneratorType:
        return self._generator_type

    @property
    def value(self) -> int:
        return self._value


class _Modulator:
    @staticmethod
    def discard_data(reader: BufferedIOBase, size: int) -> None:
        if int(size % 10) != 0:
            raise Exception("The modulator list is invalid.")

        reader.seek(size, io.SEEK_CUR)


class _SampleType(IntEnum):
    NONE = 0
    MONO = 1
    RIGHT = 2
    LEFT = 4
    LINKED = 8
    ROM_MONO = 0x8001
    ROM_RIGHT = 0x8002
    ROM_LEFT = 0x8004
    ROM_LINKED = 0x8008


class SampleHeader:
    _name: str
    _start: int
    _end: int
    _start_loop: int
    _end_loop: int
    _sample_rate: int
    _original_pitch: int
    _pitch_correction: int
    _link: int
    _sample_type: _SampleType

    def __init__(self, reader: BufferedIOBase) -> None:
        self._name = _BinaryReaderEx.read_fixed_length_string(reader, 20)
        self._start = _BinaryReaderEx.read_int32(reader)
        self._end = _BinaryReaderEx.read_int32(reader)
        self._start_loop = _BinaryReaderEx.read_int32(reader)
        self._end_loop = _BinaryReaderEx.read_int32(reader)
        self._sample_rate = _BinaryReaderEx.read_int32(reader)
        self._original_pitch = _BinaryReaderEx.read_uint8(reader)
        self._pitch_correction = _BinaryReaderEx.read_int8(reader)
        self._link = _BinaryReaderEx.read_uint16(reader)
        self._sample_type = _SampleType(_BinaryReaderEx.read_uint16(reader))

    @staticmethod
    def _read_from_chunk(reader: BufferedIOBase, size: int) -> Sequence["SampleHeader"]:
        if int(size % 46) != 0:
            raise Exception("The sample header list is invalid.")

        count = int(size / 46) - 1
        headers = list[SampleHeader]()

        for _ in range(count):
            headers.append(SampleHeader(reader))

        # The last one is the terminator.
        SampleHeader(reader)

        return headers

    @property
    def name(self) -> str:
        return self._name

    @property
    def start(self) -> int:
        return self._start

    @property
    def end(self) -> int:
        return self._end

    @property
    def start_loop(self) -> int:
        return self._start_loop

    @property
    def end_loop(self) -> int:
        return self._end_loop

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def original_pitch(self) -> int:
        return self._original_pitch

    @property
    def pitch_correction(self) -> int:
        return self._pitch_correction


class _ZoneInfo:
    _generator_index: int
    _modulator_index: int
    _generator_count: int
    _modulator_count: int

    def __init__(self, reader: BufferedIOBase) -> None:
        self._generator_index = _BinaryReaderEx.read_uint16(reader)
        self._modulator_index = _BinaryReaderEx.read_uint16(reader)

    @staticmethod
    def read_from_chunk(reader: BufferedIOBase, size: int) -> Sequence["_ZoneInfo"]:
        if int(size % 4) != 0:
            raise Exception("The zone list is invalid.")

        count = int(size / 4)
        zones = list[_ZoneInfo]()

        for i in range(count):
            zones.append(_ZoneInfo(reader))

        for i in range(count - 1):
            zones[i]._generator_count = (
                zones[i + 1]._generator_index - zones[i]._generator_index
            )
            zones[i]._modulator_count = (
                zones[i + 1]._modulator_index - zones[i]._modulator_index
            )

        return zones

    @property
    def generator_index(self) -> int:
        return self._generator_index

    @property
    def modulator_index(self) -> int:
        return self._modulator_index

    @property
    def generator_count(self) -> int:
        return self._generator_count

    @property
    def modulator_count(self) -> int:
        return self._modulator_count


class _Zone:
    _generators: Sequence[_Generator]

    def __init__(self, generators: Sequence[_Generator]) -> None:
        self._generators = generators

    @staticmethod
    def create(
        infos: Sequence[_ZoneInfo], generators: Sequence[_Generator]
    ) -> Sequence["_Zone"]:
        if len(infos) <= 1:
            raise Exception("No valid zone was found.")

        # The last one is the terminator.
        count = len(infos) - 1
        zones = list[_Zone]()

        for i in range(count):
            info: _ZoneInfo = infos[i]

            gs = list[_Generator]()
            for j in range(info.generator_count):
                gs.append(generators[info.generator_index + j])

            zones.append(_Zone(gs))

        return zones

    @staticmethod
    def empty():
        return _Zone(list[_Generator]())

    @property
    def generators(self) -> Sequence[_Generator]:
        return self._generators


class _PresetInfo:
    _name: str
    _patch_number: int
    _bank_number: int
    _zone_start_index: int
    _zone_end_index: int
    _library: int
    _genre: int
    _morphology: int

    def __init__(self, reader: BufferedIOBase) -> None:
        self._name = _BinaryReaderEx.read_fixed_length_string(reader, 20)
        self._patch_number = _BinaryReaderEx.read_uint16(reader)
        self._bank_number = _BinaryReaderEx.read_uint16(reader)
        self._zone_start_index = _BinaryReaderEx.read_uint16(reader)
        self._library = _BinaryReaderEx.read_int32(reader)
        self._genre = _BinaryReaderEx.read_int32(reader)
        self._morphology = _BinaryReaderEx.read_int32(reader)

    @staticmethod
    def read_from_chunk(reader: BufferedIOBase, size: int) -> Sequence["_PresetInfo"]:
        if int(size % 38) != 0:
            raise Exception("The preset list is invalid.")

        count = int(size / 38)
        presets = list[_PresetInfo]()

        for i in range(count):
            presets.append(_PresetInfo(reader))

        for i in range(count - 1):
            presets[i]._zone_end_index = presets[i + 1].zone_start_index - 1

        return presets

    @property
    def name(self) -> str:
        return self._name

    @property
    def patch_number(self) -> int:
        return self._patch_number

    @property
    def bank_number(self) -> int:
        return self._bank_number

    @property
    def zone_start_index(self) -> int:
        return self._zone_start_index

    @property
    def zone_end_index(self) -> int:
        return self._zone_end_index

    @property
    def library(self) -> int:
        return self._library

    @property
    def genre(self) -> int:
        return self._genre

    @property
    def morphology(self) -> int:
        return self._morphology


class _InstrumentInfo:
    _name: str
    _zone_start_index: int
    _zone_end_index: int

    def __init__(self, reader: BufferedIOBase) -> None:
        self._name = _BinaryReaderEx.read_fixed_length_string(reader, 20)
        self._zone_start_index = _BinaryReaderEx.read_uint16(reader)

    @staticmethod
    def read_from_chunk(
        reader: BufferedIOBase, size: int
    ) -> Sequence["_InstrumentInfo"]:
        if int(size % 22) != 0:
            raise Exception("The instrument list is invalid.")

        count = int(size / 22)
        instruments = list[_InstrumentInfo]()

        for i in range(count):
            instruments.append(_InstrumentInfo(reader))

        for i in range(count - 1):
            instruments[i]._zone_end_index = instruments[i + 1]._zone_start_index - 1

        return instruments

    @property
    def name(self) -> str:
        return self._name

    @property
    def zone_start_index(self) -> int:
        return self._zone_start_index

    @property
    def zone_end_index(self) -> int:
        return self._zone_end_index


class Instrument:
    _name: str
    _regions: Sequence["InstrumentRegion"]

    def __init__(
        self,
        info: _InstrumentInfo,
        zones: Sequence[_Zone],
        samples: Sequence[SampleHeader],
    ) -> None:
        self._name = info.name

        zone_count = info.zone_end_index - info.zone_start_index + 1
        if zone_count <= 0:
            raise Exception("The instrument '" + info.name + "' has no zone.")

        zone_span = zones[info.zone_start_index : info.zone_start_index + zone_count]

        self._regions = InstrumentRegion._create(self, zone_span, samples)  # type: ignore

    @staticmethod
    def _create(
        infos: Sequence[_InstrumentInfo],
        zones: Sequence[_Zone],
        samples: Sequence[SampleHeader],
    ) -> Sequence["Instrument"]:
        if len(infos) <= 1:
            raise Exception("No valid instrument was found.")

        # The last one is the terminator.
        count = len(infos) - 1
        instruments = list[Instrument]()

        for i in range(count):
            instruments.append(Instrument(infos[i], zones, samples))

        return instruments

    @property
    def name(self) -> str:
        return self._name

    @property
    def regions(self) -> Sequence["InstrumentRegion"]:
        return self._regions


class LoopMode(IntEnum):
    NO_LOOP = 0
    CONTINUOUS = 1
    LOOP_UNTIL_NOTE_OFF = 3


class InstrumentRegion:
    _sample: SampleHeader
    _gs: MutableSequence[int]

    def __init__(
        self,
        instrument: Instrument,
        global_zone: _Zone,
        local_zone: _Zone,
        samples: Sequence[SampleHeader],
    ) -> None:
        self._gs = array("h", itertools.repeat(0, 61))
        self._gs[_GeneratorType.INITIAL_FILTER_CUTOFF_FREQUENCY] = 13500
        self._gs[_GeneratorType.DELAY_MODULATION_LFO] = -12000
        self._gs[_GeneratorType.DELAY_VIBRATO_LFO] = -12000
        self._gs[_GeneratorType.DELAY_MODULATION_ENVELOPE] = -12000
        self._gs[_GeneratorType.ATTACK_MODULATION_ENVELOPE] = -12000
        self._gs[_GeneratorType.HOLD_MODULATION_ENVELOPE] = -12000
        self._gs[_GeneratorType.DECAY_MODULATION_ENVELOPE] = -12000
        self._gs[_GeneratorType.RELEASE_MODULATION_ENVELOPE] = -12000
        self._gs[_GeneratorType.DELAY_VOLUME_ENVELOPE] = -12000
        self._gs[_GeneratorType.ATTACK_VOLUME_ENVELOPE] = -12000
        self._gs[_GeneratorType.HOLD_VOLUME_ENVELOPE] = -12000
        self._gs[_GeneratorType.DECAY_VOLUME_ENVELOPE] = -12000
        self._gs[_GeneratorType.RELEASE_VOLUME_ENVELOPE] = -12000
        self._gs[_GeneratorType.KEY_RANGE] = 0x7F00
        self._gs[_GeneratorType.VELOCITY_RANGE] = 0x7F00
        self._gs[_GeneratorType.KEY_NUMBER] = -1
        self._gs[_GeneratorType.VELOCITY] = -1
        self._gs[_GeneratorType.SCALE_TUNING] = 100
        self._gs[_GeneratorType.OVERRIDING_ROOT_KEY] = -1

        for generator in global_zone.generators:
            self._set_parameter(generator)

        for generator in local_zone.generators:
            self._set_parameter(generator)

        id = self._gs[_GeneratorType.SAMPLE_ID]
        if not (0 <= id and id < len(samples)):
            raise Exception(
                "The instrument '"
                + instrument.name
                + "' contains an invalid sample ID '"
                + str(id)
                + "'."
            )
        self._sample = samples[id]

    @staticmethod
    def _create(
        instrument: Instrument, zones: Sequence[_Zone], samples: Sequence[SampleHeader]
    ) -> Sequence["InstrumentRegion"]:
        # Is the first one the global zone?
        if (
            len(zones[0].generators) == 0
            or zones[0].generators[-1].generator_type != _GeneratorType.SAMPLE_ID
        ):
            # The first one is the global zone.
            global_zone = zones[0]

            # The global zone is regarded as the base setting of subsequent zones.
            count = len(zones) - 1
            regions = list[InstrumentRegion]()
            for i in range(count):
                regions.append(
                    InstrumentRegion(instrument, global_zone, zones[i + 1], samples)
                )
            return regions

        else:
            # No global zone.
            count = len(zones)
            regions = list[InstrumentRegion]()
            for i in range(count):
                regions.append(
                    InstrumentRegion(instrument, _Zone.empty(), zones[i], samples)
                )
            return regions

    def _set_parameter(self, generator: _Generator) -> None:
        index = int(generator.generator_type)

        # Unknown generators should be ignored.
        if 0 <= index and index < len(self._gs):
            self._gs[index] = generator.value

    def contains(self, key: int, velocity: int) -> bool:
        contains_key = self.key_range_start <= key and key <= self.key_range_end
        contains_velocity = (
            self.velocity_range_start <= velocity
            and velocity <= self.velocity_range_end
        )
        return contains_key and contains_velocity

    @property
    def sample(self) -> SampleHeader:
        return self._sample

    @property
    def sample_start(self) -> int:
        return self._sample.start + self.start_address_offset

    @property
    def sample_end(self) -> int:
        return self._sample.end + self.end_address_offset

    @property
    def sample_start_loop(self) -> int:
        return self._sample.start_loop + self.start_loop_address_offset

    @property
    def sample_end_loop(self) -> int:
        return self._sample.end_loop + self.end_loop_address_offset

    @property
    def start_address_offset(self) -> int:
        return (
            32768 * self._gs[_GeneratorType.START_ADDRESS_COARSE_OFFSET]
            + self._gs[_GeneratorType.START_ADDRESS_OFFSET]
        )

    @property
    def end_address_offset(self) -> int:
        return (
            32768 * self._gs[_GeneratorType.END_ADDRESS_COARSE_OFFSET]
            + self._gs[_GeneratorType.END_ADDRESS_OFFSET]
        )

    @property
    def start_loop_address_offset(self) -> int:
        return (
            32768 * self._gs[_GeneratorType.START_LOOP_ADDRESS_COARSE_OFFSET]
            + self._gs[_GeneratorType.START_LOOP_ADDRESS_OFFSET]
        )

    @property
    def end_loop_address_offset(self) -> int:
        return (
            32768 * self._gs[_GeneratorType.END_LOOP_ADDRESS_COARSE_OFFSET]
            + self._gs[_GeneratorType.END_LOOP_ADDRESS_OFFSET]
        )

    @property
    def modulation_lfo_to_pitch(self) -> int:
        return self._gs[_GeneratorType.MODULATION_LFO_TO_PITCH]

    @property
    def vibrato_lfo_to_pitch(self) -> int:
        return self._gs[_GeneratorType.VIBRATO_LFO_TO_PITCH]

    @property
    def modulation_envelope_to_pitch(self) -> int:
        return self._gs[_GeneratorType.MODULATION_ENVELOPE_TO_PITCH]

    @property
    def initial_filter_cutoff_frequency(self) -> float:
        return _SoundFontMath.cents_to_hertz(
            self._gs[_GeneratorType.INITIAL_FILTER_CUTOFF_FREQUENCY]
        )

    @property
    def initial_filter_q(self) -> float:
        return 0.1 * self._gs[_GeneratorType.INITIAL_FILTER_Q]

    @property
    def modulation_lfo_to_filter_cutoff_frequency(self) -> int:
        return self._gs[_GeneratorType.MODULATION_LFO_TO_FILTER_CUTOFF_FREQUENCY]

    @property
    def modulation_envelope_to_filter_cutoff_frequency(self) -> int:
        return self._gs[_GeneratorType.MODULATION_ENVELOPE_TO_FILTER_CUTOFF_FREQUENCY]

    @property
    def modulation_lfo_to_volume(self) -> float:
        return 0.1 * self._gs[_GeneratorType.MODULATION_LFO_TO_VOLUME]

    @property
    def chorus_effects_send(self) -> float:
        return 0.1 * self._gs[_GeneratorType.CHORUS_EFFECTS_SEND]

    @property
    def reverb_effects_send(self) -> float:
        return 0.1 * self._gs[_GeneratorType.REVERB_EFFECTS_SEND]

    @property
    def pan(self) -> float:
        return 0.1 * self._gs[_GeneratorType.PAN]

    @property
    def delay_modulation_lfo(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.DELAY_MODULATION_LFO]
        )

    @property
    def frequency_modulation_lfo(self) -> float:
        return _SoundFontMath.cents_to_hertz(
            self._gs[_GeneratorType.FREQUENCY_MODULATION_LFO]
        )

    @property
    def delay_vibrato_lfo(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.DELAY_VIBRATO_LFO]
        )

    @property
    def frequency_vibrato_lfo(self) -> float:
        return _SoundFontMath.cents_to_hertz(
            self._gs[_GeneratorType.FREQUENCY_VIBRATO_LFO]
        )

    @property
    def delay_modulation_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.DELAY_MODULATION_ENVELOPE]
        )

    @property
    def attack_modulation_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.ATTACK_MODULATION_ENVELOPE]
        )

    @property
    def hold_modulation_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.HOLD_MODULATION_ENVELOPE]
        )

    @property
    def decay_modulation_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.DECAY_MODULATION_ENVELOPE]
        )

    @property
    def sustain_modulation_envelope(self) -> float:
        return 0.1 * self._gs[_GeneratorType.SUSTAIN_MODULATION_ENVELOPE]

    @property
    def release_modulation_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.RELEASE_MODULATION_ENVELOPE]
        )

    @property
    def key_number_to_modulation_envelope_hold(self) -> int:
        return self._gs[_GeneratorType.KEY_NUMBER_TO_MODULATION_ENVELOPE_HOLD]

    @property
    def key_number_to_modulation_envelope_decay(self) -> int:
        return self._gs[_GeneratorType.KEY_NUMBER_TO_MODULATION_ENVELOPE_DECAY]

    @property
    def delay_volume_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.DELAY_VOLUME_ENVELOPE]
        )

    @property
    def attack_volume_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.ATTACK_VOLUME_ENVELOPE]
        )

    @property
    def hold_volume_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.HOLD_VOLUME_ENVELOPE]
        )

    @property
    def decay_volume_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.DECAY_VOLUME_ENVELOPE]
        )

    @property
    def sustain_volume_envelope(self) -> float:
        return 0.1 * self._gs[_GeneratorType.SUSTAIN_VOLUME_ENVELOPE]

    @property
    def release_volume_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self._gs[_GeneratorType.RELEASE_VOLUME_ENVELOPE]
        )

    @property
    def key_number_to_volume_envelope_hold(self) -> int:
        return self._gs[_GeneratorType.KEY_NUMBER_TO_VOLUME_ENVELOPE_HOLD]

    @property
    def key_number_to_volume_envelope_decay(self) -> int:
        return self._gs[_GeneratorType.KEY_NUMBER_TO_VOLUME_ENVELOPE_DECAY]

    @property
    def key_range_start(self) -> int:
        return self._gs[_GeneratorType.KEY_RANGE] & 0xFF

    @property
    def key_range_end(self) -> int:
        return (self._gs[_GeneratorType.KEY_RANGE] >> 8) & 0xFF

    @property
    def velocity_range_start(self) -> int:
        return self._gs[_GeneratorType.VELOCITY_RANGE] & 0xFF

    @property
    def velocity_range_end(self) -> int:
        return (self._gs[_GeneratorType.VELOCITY_RANGE] >> 8) & 0xFF

    @property
    def initial_attenuation(self) -> float:
        return 0.1 * self._gs[_GeneratorType.INITIAL_ATTENUATION]

    @property
    def coarse_tune(self) -> int:
        return self._gs[_GeneratorType.COARSE_TUNE]

    @property
    def fine_tune(self) -> int:
        return self._gs[_GeneratorType.FINE_TUNE] + self._sample.pitch_correction

    @property
    def sample_modes(self) -> LoopMode:
        return (
            LoopMode(self._gs[_GeneratorType.SAMPLE_MODES])
            if self._gs[_GeneratorType.SAMPLE_MODES] != 2
            else LoopMode.NO_LOOP
        )

    @property
    def scale_tuning(self) -> int:
        return self._gs[_GeneratorType.SCALE_TUNING]

    @property
    def exclusive_class(self) -> int:
        return self._gs[_GeneratorType.EXCLUSIVE_CLASS]

    @property
    def root_key(self) -> int:
        return (
            self._gs[_GeneratorType.OVERRIDING_ROOT_KEY]
            if self._gs[_GeneratorType.OVERRIDING_ROOT_KEY] != -1
            else self._sample.original_pitch
        )


class Preset:
    _name: str
    _patch_number: int
    _bank_number: int
    _library: int
    _genre: int
    _morphology: int
    _regions: Sequence["PresetRegion"]

    def __init__(
        self,
        info: _PresetInfo,
        zones: Sequence[_Zone],
        instruments: Sequence[Instrument],
    ) -> None:
        self._name = info.name
        self._patch_number = info.patch_number
        self._bank_number = info.bank_number
        self._library = info.library
        self._genre = info.genre
        self._morphology = info.morphology

        zone_count = info.zone_end_index - info.zone_start_index + 1
        if zone_count <= 0:
            raise Exception("The preset '" + info.name + "' has no zone.")

        zone_span = zones[info.zone_start_index : info.zone_start_index + zone_count]

        self._regions = PresetRegion._create(self, zone_span, instruments)  # type: ignore

    @staticmethod
    def _create(
        infos: Sequence[_PresetInfo],
        zones: Sequence[_Zone],
        instruments: Sequence[Instrument],
    ) -> Sequence["Preset"]:
        if len(infos) <= 1:
            raise Exception("No valid preset was found.")

        # The last one is the terminator.
        count = len(infos) - 1
        presets = list[Preset]()

        for i in range(count):
            presets.append(Preset(infos[i], zones, instruments))

        return presets

    @property
    def name(self) -> str:
        return self._name

    @property
    def patch_number(self) -> int:
        return self._patch_number

    @property
    def bank_number(self) -> int:
        return self._bank_number

    @property
    def library(self) -> int:
        return self._library

    @property
    def genre(self) -> int:
        return self._genre

    @property
    def morphology(self) -> int:
        return self._morphology

    @property
    def regions(self) -> Sequence["PresetRegion"]:
        return self._regions


class PresetRegion:
    _instrument: Instrument
    _gs: MutableSequence[int]

    def __init__(
        self,
        preset: Preset,
        global_zone: _Zone,
        local_zone: _Zone,
        instruments: Sequence[Instrument],
    ) -> None:
        self._gs = array("h", itertools.repeat(0, 61))
        self._gs[_GeneratorType.KEY_RANGE] = 0x7F00
        self._gs[_GeneratorType.VELOCITY_RANGE] = 0x7F00

        for generator in global_zone.generators:
            self._set_parameter(generator)

        for generator in local_zone.generators:
            self._set_parameter(generator)

        id = self._gs[_GeneratorType.INSTRUMENT]
        if not (0 <= id and id < len(instruments)):
            raise Exception(
                "The preset '"
                + preset.name
                + "' contains an invalid instrument ID '"
                + str(id)
                + "'."
            )
        self._instrument = instruments[id]

    @staticmethod
    def _create(
        preset: Preset, zones: Sequence[_Zone], instruments: Sequence[Instrument]
    ) -> Sequence["PresetRegion"]:
        # Is the first one the global zone?
        if (
            len(zones[0].generators) == 0
            or zones[0].generators[-1].generator_type != _GeneratorType.INSTRUMENT
        ):
            # The first one is the global zone.
            global_zone = zones[0]

            # The global zone is regarded as the base setting of subsequent zones.
            count = len(zones) - 1
            regions = list[PresetRegion]()
            for i in range(count):
                regions.append(
                    PresetRegion(preset, global_zone, zones[i + 1], instruments)
                )
            return regions

        else:
            # No global zone.
            count = len(zones)
            regions = list[PresetRegion]()
            for i in range(count):
                regions.append(
                    PresetRegion(preset, _Zone.empty(), zones[i], instruments)
                )
            return regions

    def _set_parameter(self, generator: _Generator) -> None:
        index = int(generator.generator_type)

        # Unknown generators should be ignored.
        if 0 <= index and index < len(self._gs):
            self._gs[index] = generator.value

    def contains(self, key: int, velocity: int) -> bool:
        contains_key = self.key_range_start <= key and key <= self.key_range_end
        contains_velocity = (
            self.velocity_range_start <= velocity
            and velocity <= self.velocity_range_end
        )
        return contains_key and contains_velocity

    @property
    def instrument(self) -> Instrument:
        return self._instrument

    @property
    def modulation_lfo_to_pitch(self) -> int:
        return self._gs[_GeneratorType.MODULATION_LFO_TO_PITCH]

    @property
    def vibrato_lfo_to_pitch(self) -> int:
        return self._gs[_GeneratorType.VIBRATO_LFO_TO_PITCH]

    @property
    def modulation_envelope_to_pitch(self) -> int:
        return self._gs[_GeneratorType.MODULATION_ENVELOPE_TO_PITCH]

    @property
    def initial_filter_cutoff_frequency(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.INITIAL_FILTER_CUTOFF_FREQUENCY]
        )

    @property
    def initial_filter_q(self) -> float:
        return 0.1 * self._gs[_GeneratorType.INITIAL_FILTER_Q]

    @property
    def modulation_lfo_to_filter_cutoff_frequency(self) -> int:
        return self._gs[_GeneratorType.MODULATION_LFO_TO_FILTER_CUTOFF_FREQUENCY]

    @property
    def modulation_envelope_to_filter_cutoff_frequency(self) -> int:
        return self._gs[_GeneratorType.MODULATION_ENVELOPE_TO_FILTER_CUTOFF_FREQUENCY]

    @property
    def modulation_lfo_to_volume(self) -> float:
        return 0.1 * self._gs[_GeneratorType.MODULATION_LFO_TO_VOLUME]

    @property
    def chorus_effects_send(self) -> float:
        return 0.1 * self._gs[_GeneratorType.CHORUS_EFFECTS_SEND]

    @property
    def reverb_effects_send(self) -> float:
        return 0.1 * self._gs[_GeneratorType.REVERB_EFFECTS_SEND]

    @property
    def pan(self) -> float:
        return 0.1 * self._gs[_GeneratorType.PAN]

    @property
    def delay_modulation_lfo(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.DELAY_MODULATION_LFO]
        )

    @property
    def frequency_modulation_lfo(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.FREQUENCY_MODULATION_LFO]
        )

    @property
    def delay_vibrato_lfo(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.DELAY_VIBRATO_LFO]
        )

    @property
    def frequency_vibrato_lfo(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.FREQUENCY_VIBRATO_LFO]
        )

    @property
    def delay_modulation_envelope(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.DELAY_MODULATION_ENVELOPE]
        )

    @property
    def attack_modulation_envelope(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.ATTACK_MODULATION_ENVELOPE]
        )

    @property
    def hold_modulation_envelope(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.HOLD_MODULATION_ENVELOPE]
        )

    @property
    def decay_modulation_envelope(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.DECAY_MODULATION_ENVELOPE]
        )

    @property
    def sustain_modulation_envelope(self) -> float:
        return 0.1 * self._gs[_GeneratorType.SUSTAIN_MODULATION_ENVELOPE]

    @property
    def release_modulation_envelope(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.RELEASE_MODULATION_ENVELOPE]
        )

    @property
    def key_number_to_modulation_envelope_hold(self) -> int:
        return self._gs[_GeneratorType.KEY_NUMBER_TO_MODULATION_ENVELOPE_HOLD]

    @property
    def key_number_to_modulation_envelope_decay(self) -> int:
        return self._gs[_GeneratorType.KEY_NUMBER_TO_MODULATION_ENVELOPE_DECAY]

    @property
    def delay_volume_envelope(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.DELAY_VOLUME_ENVELOPE]
        )

    @property
    def attack_volume_envelope(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.ATTACK_VOLUME_ENVELOPE]
        )

    @property
    def hold_volume_envelope(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.HOLD_VOLUME_ENVELOPE]
        )

    @property
    def decay_volume_envelope(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.DECAY_VOLUME_ENVELOPE]
        )

    @property
    def sustain_volume_envelope(self) -> float:
        return 0.1 * self._gs[_GeneratorType.SUSTAIN_VOLUME_ENVELOPE]

    @property
    def release_volume_envelope(self) -> float:
        return _SoundFontMath.cents_to_multiplying_factor(
            self._gs[_GeneratorType.RELEASE_VOLUME_ENVELOPE]
        )

    @property
    def key_number_to_volume_envelope_hold(self) -> int:
        return self._gs[_GeneratorType.KEY_NUMBER_TO_VOLUME_ENVELOPE_HOLD]

    @property
    def key_number_to_volume_envelope_decay(self) -> int:
        return self._gs[_GeneratorType.KEY_NUMBER_TO_VOLUME_ENVELOPE_DECAY]

    @property
    def key_range_start(self) -> int:
        return self._gs[_GeneratorType.KEY_RANGE] & 0xFF

    @property
    def key_range_end(self) -> int:
        return (self._gs[_GeneratorType.KEY_RANGE] >> 8) & 0xFF

    @property
    def velocity_range_start(self) -> int:
        return self._gs[_GeneratorType.VELOCITY_RANGE] & 0xFF

    @property
    def velocity_range_end(self) -> int:
        return (self._gs[_GeneratorType.VELOCITY_RANGE] >> 8) & 0xFF

    @property
    def initial_attenuation(self) -> float:
        return 0.1 * self._gs[_GeneratorType.INITIAL_ATTENUATION]

    @property
    def coarse_tune(self) -> int:
        return self._gs[_GeneratorType.COARSE_TUNE]

    @property
    def fine_tune(self) -> int:
        return self._gs[_GeneratorType.FINE_TUNE]

    @property
    def scale_tuning(self) -> int:
        return self._gs[_GeneratorType.SCALE_TUNING]


class _SoundFontParameters:
    _sample_headers: Sequence[SampleHeader]
    _presets: Sequence[Preset]
    _instruments: Sequence[Instrument]

    def __init__(self, reader: BufferedIOBase) -> None:
        chunk_id = _BinaryReaderEx.read_four_cc(reader)
        if chunk_id != "LIST":
            raise Exception("The LIST chunk was not found.")

        end = _BinaryReaderEx.read_int32(reader)
        end += reader.tell()

        list_type = _BinaryReaderEx.read_four_cc(reader)
        if list_type != "pdta":
            raise Exception(
                "The type of the LIST chunk must be 'pdta', but was '"
                + list_type
                + "'."
            )

        preset_infos: Optional[Sequence[_PresetInfo]] = None
        preset_bag: Optional[Sequence[_ZoneInfo]] = None
        preset_generators: Optional[Sequence[_Generator]] = None
        instrument_infos: Optional[Sequence[_InstrumentInfo]] = None
        instrument_bag: Optional[Sequence[_ZoneInfo]] = None
        instrument_generators: Optional[Sequence[_Generator]] = None
        sample_headers: Optional[Sequence[SampleHeader]] = None

        while reader.tell() < end:
            id = _BinaryReaderEx.read_four_cc(reader)
            size = _BinaryReaderEx.read_uint32(reader)

            match id:
                case "phdr":
                    preset_infos = _PresetInfo.read_from_chunk(reader, size)

                case "pbag":
                    preset_bag = _ZoneInfo.read_from_chunk(reader, size)

                case "pmod":
                    _Modulator.discard_data(reader, size)

                case "pgen":
                    preset_generators = _Generator.read_from_chunk(reader, size)

                case "inst":
                    instrument_infos = _InstrumentInfo.read_from_chunk(reader, size)

                case "ibag":
                    instrument_bag = _ZoneInfo.read_from_chunk(reader, size)

                case "imod":
                    _Modulator.discard_data(reader, size)

                case "igen":
                    instrument_generators = _Generator.read_from_chunk(reader, size)

                case "shdr":
                    sample_headers = SampleHeader._read_from_chunk(reader, size)  # type: ignore

                case _:
                    raise Exception(
                        "The INFO list contains an unknown ID '" + id + "'."
                    )

        if preset_infos is None:
            raise Exception("The PHDR sub-chunk was not found.")

        if preset_bag is None:
            raise Exception("The PBAG sub-chunk was not found.")

        if preset_generators is None:
            raise Exception("The PGEN sub-chunk was not found.")

        if instrument_infos is None:
            raise Exception("The INST sub-chunk was not found.")

        if instrument_bag is None:
            raise Exception("The IBAG sub-chunk was not found.")

        if instrument_generators is None:
            raise Exception("The IGEN sub-chunk was not found.")

        if sample_headers is None:
            raise Exception("The SHDR sub-chunk was not found.")

        self._sample_headers = sample_headers

        instrument_zones = _Zone.create(instrument_bag, instrument_generators)
        self._instruments = Instrument._create(  # type: ignore
            instrument_infos, instrument_zones, sample_headers
        )

        preset_zones = _Zone.create(preset_bag, preset_generators)
        self._presets = Preset._create(preset_infos, preset_zones, self._instruments)  # type: ignore

    @property
    def sample_headers(self) -> Sequence[SampleHeader]:
        return self._sample_headers

    @property
    def presets(self) -> Sequence[Preset]:
        return self._presets

    @property
    def instruments(self) -> Sequence[Instrument]:
        return self._instruments


class SoundFont:
    _info: SoundFontInfo
    _bits_per_sample: int
    _wave_data: Sequence[float]
    _sample_headers: Sequence[SampleHeader]
    _presets: Sequence[Preset]
    _instruments: Sequence[Instrument]

    def __init__(self, reader: BufferedIOBase) -> None:
        chunk_id = _BinaryReaderEx.read_four_cc(reader)
        if chunk_id != "RIFF":
            raise Exception("The RIFF chunk was not found.")

        _BinaryReaderEx.read_uint32(reader)

        form_type = _BinaryReaderEx.read_four_cc(reader)
        if form_type != "sfbk":
            raise Exception(
                "The type of the RIFF chunk must be 'sfbk', but was '"
                + form_type
                + "'."
            )

        self._info = SoundFontInfo(reader)

        sample_data = _SoundFontSampleData(reader)
        self._bits_per_sample = sample_data.bits_per_sample
        self._wave_data = sample_data.samples

        parameters = _SoundFontParameters(reader)
        self._sample_headers = parameters.sample_headers
        self._presets = parameters.presets
        self._instruments = parameters.instruments

    @classmethod
    def from_file(cls, file_path: str) -> "SoundFont":
        with open(file_path, "rb") as f:
            return cls(f)

    @property
    def info(self) -> SoundFontInfo:
        return self._info

    @property
    def wave_data(self) -> Sequence[float]:
        return self._wave_data

    @property
    def sample_headers(self) -> Sequence[SampleHeader]:
        return self._sample_headers

    @property
    def presets(self) -> Sequence[Preset]:
        return self._presets

    @property
    def instruments(self) -> Sequence[Instrument]:
        return self._instruments


class _RegionPair:
    _preset: PresetRegion
    _instrument: InstrumentRegion

    def __init__(self, preset: PresetRegion, instrument: InstrumentRegion) -> None:
        self._preset = preset
        self._instrument = instrument

    def get_value(self, generator_type: _GeneratorType) -> int:
        return self._preset._gs[generator_type] + self._instrument._gs[generator_type]  # type: ignore

    @property
    def preset(self) -> PresetRegion:
        return self._preset

    @property
    def instrument(self) -> InstrumentRegion:
        return self._instrument

    @property
    def sample_start(self) -> int:
        return self._instrument.sample_start

    @property
    def sample_end(self) -> int:
        return self._instrument.sample_end

    @property
    def sample_start_loop(self) -> int:
        return self._instrument.sample_start_loop

    @property
    def sample_end_loop(self) -> int:
        return self._instrument.sample_end_loop

    @property
    def start_address_offset(self) -> int:
        return self._instrument.start_address_offset

    @property
    def end_address_offset(self) -> int:
        return self._instrument.end_address_offset

    @property
    def start_loop_address_offset(self) -> int:
        return self._instrument.start_loop_address_offset

    @property
    def end_loop_address_offset(self) -> int:
        return self._instrument.end_loop_address_offset

    @property
    def modulation_lfo_to_pitch(self) -> int:
        return self.get_value(_GeneratorType.MODULATION_LFO_TO_PITCH)

    @property
    def vibrato_lfo_to_pitch(self) -> int:
        return self.get_value(_GeneratorType.VIBRATO_LFO_TO_PITCH)

    @property
    def modulation_envelope_to_pitch(self) -> int:
        return self.get_value(_GeneratorType.MODULATION_ENVELOPE_TO_PITCH)

    @property
    def initial_filter_cutoff_frequency(self) -> float:
        return _SoundFontMath.cents_to_hertz(
            self.get_value(_GeneratorType.INITIAL_FILTER_CUTOFF_FREQUENCY)
        )

    @property
    def initial_filter_q(self) -> float:
        return 0.1 * self.get_value(_GeneratorType.INITIAL_FILTER_Q)

    @property
    def modulation_lfo_to_filter_cutoff_frequency(self) -> int:
        return self.get_value(_GeneratorType.MODULATION_LFO_TO_FILTER_CUTOFF_FREQUENCY)

    @property
    def modulation_envelope_to_filter_cutoff_frequency(self) -> int:
        return self.get_value(
            _GeneratorType.MODULATION_ENVELOPE_TO_FILTER_CUTOFF_FREQUENCY
        )

    @property
    def modulation_lfo_to_volume(self) -> float:
        return 0.1 * self.get_value(_GeneratorType.MODULATION_LFO_TO_VOLUME)

    @property
    def chorus_effects_send(self) -> float:
        return 0.1 * self.get_value(_GeneratorType.CHORUS_EFFECTS_SEND)

    @property
    def reverb_effects_send(self) -> float:
        return 0.1 * self.get_value(_GeneratorType.REVERB_EFFECTS_SEND)

    @property
    def pan(self) -> float:
        return 0.1 * self.get_value(_GeneratorType.PAN)

    @property
    def delay_modulation_lfo(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.DELAY_MODULATION_LFO)
        )

    @property
    def frequency_modulation_lfo(self) -> float:
        return _SoundFontMath.cents_to_hertz(
            self.get_value(_GeneratorType.FREQUENCY_MODULATION_LFO)
        )

    @property
    def delay_vibrato_lfo(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.DELAY_VIBRATO_LFO)
        )

    @property
    def frequency_vibrato_lfo(self) -> float:
        return _SoundFontMath.cents_to_hertz(
            self.get_value(_GeneratorType.FREQUENCY_VIBRATO_LFO)
        )

    @property
    def delay_modulation_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.DELAY_MODULATION_ENVELOPE)
        )

    @property
    def attack_modulation_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.ATTACK_MODULATION_ENVELOPE)
        )

    @property
    def hold_modulation_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.HOLD_MODULATION_ENVELOPE)
        )

    @property
    def decay_modulation_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.DECAY_MODULATION_ENVELOPE)
        )

    @property
    def sustain_modulation_envelope(self) -> float:
        return 0.1 * self.get_value(_GeneratorType.SUSTAIN_MODULATION_ENVELOPE)

    @property
    def release_modulation_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.RELEASE_MODULATION_ENVELOPE)
        )

    @property
    def key_number_to_modulation_envelope_hold(self) -> int:
        return self.get_value(_GeneratorType.KEY_NUMBER_TO_MODULATION_ENVELOPE_HOLD)

    @property
    def key_number_to_modulation_envelope_decay(self) -> int:
        return self.get_value(_GeneratorType.KEY_NUMBER_TO_MODULATION_ENVELOPE_DECAY)

    @property
    def delay_volume_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.DELAY_VOLUME_ENVELOPE)
        )

    @property
    def attack_volume_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.ATTACK_VOLUME_ENVELOPE)
        )

    @property
    def hold_volume_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.HOLD_VOLUME_ENVELOPE)
        )

    @property
    def decay_volume_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.DECAY_VOLUME_ENVELOPE)
        )

    @property
    def sustain_volume_envelope(self) -> float:
        return 0.1 * self.get_value(_GeneratorType.SUSTAIN_VOLUME_ENVELOPE)

    @property
    def release_volume_envelope(self) -> float:
        return _SoundFontMath.timecents_to_seconds(
            self.get_value(_GeneratorType.RELEASE_VOLUME_ENVELOPE)
        )

    @property
    def key_number_to_volume_envelope_hold(self) -> int:
        return self.get_value(_GeneratorType.KEY_NUMBER_TO_VOLUME_ENVELOPE_HOLD)

    @property
    def key_number_to_volume_envelope_decay(self) -> int:
        return self.get_value(_GeneratorType.KEY_NUMBER_TO_VOLUME_ENVELOPE_DECAY)

    @property
    def initial_attenuation(self) -> float:
        return 0.1 * self.get_value(_GeneratorType.INITIAL_ATTENUATION)

    @property
    def coarse_tune(self) -> int:
        return self.get_value(_GeneratorType.COARSE_TUNE)

    @property
    def fine_tune(self) -> int:
        return (
            self.get_value(_GeneratorType.FINE_TUNE)
            + self._instrument.sample.pitch_correction
        )

    @property
    def sample_modes(self) -> LoopMode:
        return self._instrument.sample_modes

    @property
    def scale_tuning(self) -> int:
        return self.get_value(_GeneratorType.SCALE_TUNING)

    @property
    def exclusive_class(self) -> int:
        return self._instrument.exclusive_class

    @property
    def root_key(self) -> int:
        return self._instrument.root_key


class _Oscillator:
    _synthesizer: "Synthesizer"

    _data: Sequence[float]
    _loop_mode: LoopMode
    _sample_rate: int
    _start: int
    _end: int
    _start_loop: int
    _end_loop: int
    _root_key: int

    _tune: float
    _pitch_change_scale: float
    _sample_rate_ratio: float

    _looping: bool

    _position: float

    def __init__(self, synthesizer: "Synthesizer") -> None:
        self._synthesizer = synthesizer

    def start(
        self,
        data: Sequence[float],
        loop_mode: LoopMode,
        sample_rate: int,
        start: int,
        end: int,
        start_loop: int,
        end_loop: int,
        root_key: int,
        coarse_tune: int,
        fine_tune: int,
        scale_tuning: int,
    ) -> None:
        self._data = data
        self._loop_mode = loop_mode
        self._sample_rate = sample_rate
        self._start = start
        self._end = end
        self._start_loop = start_loop
        self._end_loop = end_loop
        self._root_key = root_key

        self._tune = coarse_tune + 0.01 * fine_tune
        self._pitch_change_scale = 0.01 * scale_tuning
        self._sample_rate_ratio = sample_rate / self._synthesizer.sample_rate

        if loop_mode == LoopMode.NO_LOOP:
            self._looping = False
        else:
            self._looping = True

        self._position = start

    def release(self) -> None:
        if self._loop_mode == LoopMode.LOOP_UNTIL_NOTE_OFF:
            self._looping = False

    def process(self, block: MutableSequence[float], pitch: float) -> bool:
        pitch_change = self._pitch_change_scale * (pitch - self._root_key) + self._tune
        pitch_ratio = self._sample_rate_ratio * math.pow(2.0, pitch_change / 12.0)
        return self.fill_block(block, pitch_ratio)

    def fill_block(self, block: MutableSequence[float], pitch_ratio: float) -> bool:
        if self._looping:
            return self.fill_block_continuous(block, pitch_ratio)
        else:
            return self.fill_block_no_loop(block, pitch_ratio)

    def fill_block_no_loop(
        self, block: MutableSequence[float], pitch_ratio: float
    ) -> bool:
        for t in range(len(block)):
            index = int(self._position)

            if index >= self._end:
                if t > 0:
                    for u in range(t, len(block)):
                        block[u] = 0
                    return True
                else:
                    return False

            x1 = self._data[index]
            x2 = self._data[index + 1]
            a = self._position - index
            block[t] = x1 + a * (x2 - x1)

            self._position += pitch_ratio

        return True

    def fill_block_continuous(
        self, block: MutableSequence[float], pitch_ratio: float
    ) -> bool:
        end_loop_position = float(self._end_loop)

        loop_length = self._end_loop - self._start_loop

        for t in range(len(block)):
            if self._position >= end_loop_position:
                self._position -= loop_length

            index1 = int(self._position)
            index2 = index1 + 1

            if index2 >= self._end_loop:
                index2 -= loop_length

            x1 = self._data[index1]
            x2 = self._data[index2]
            a = self._position - index1
            block[t] = x1 + a * (x2 - x1)

            self._position += pitch_ratio

        return True


class _EnvelopeStage(IntEnum):
    DELAY = 0
    ATTACK = 1
    HOLD = 2
    DECAY = 3
    RELEASE = 4


class _VolumeEnvelope:
    _synthesizer: "Synthesizer"

    _attack_slope: float
    _decay_slope: float
    _release_slope: float

    _attack_start_time: float
    _hold_start_time: float
    _decay_start_time: float
    _release_start_time: float

    _sustain_level: float
    _release_level: float

    _processed_sample_count: int
    _stage: _EnvelopeStage
    _value: float

    _priority: float

    def __init__(self, synthesizer: "Synthesizer") -> None:
        self._synthesizer = synthesizer

    def start(
        self,
        delay: float,
        attack: float,
        hold: float,
        decay: float,
        sustain: float,
        release: float,
    ) -> None:
        self._attack_slope = 1 / attack
        self._decay_slope = -9.226 / decay
        self._release_slope = -9.226 / release

        self._attack_start_time = delay
        self._hold_start_time = self._attack_start_time + attack
        self._decay_start_time = self._hold_start_time + hold
        self._release_start_time = 0

        self._sustain_level = _SoundFontMath.clamp(sustain, 0, 1)
        self._release_level = 0

        self._processed_sample_count = 0
        self._stage = _EnvelopeStage.DELAY
        self._value = 0

        self.process(0)

    def release(self) -> None:
        self._stage = _EnvelopeStage.RELEASE
        self._release_start_time = (
            float(self._processed_sample_count) / self._synthesizer.sample_rate
        )
        self._release_level = self._value

    def process(self, sample_count: int) -> bool:
        self._processed_sample_count += sample_count

        current_time = (
            float(self._processed_sample_count) / self._synthesizer.sample_rate
        )

        while self._stage <= _EnvelopeStage.HOLD:
            end_time: float

            match self._stage:
                case _EnvelopeStage.DELAY:
                    end_time = self._attack_start_time

                case _EnvelopeStage.ATTACK:
                    end_time = self._hold_start_time

                case _EnvelopeStage.HOLD:
                    end_time = self._decay_start_time

                case _:
                    raise Exception("Invalid envelope stage.")

            if current_time < end_time:
                break
            else:
                self._stage = _EnvelopeStage(self._stage.value + 1)

        match self._stage:
            case _EnvelopeStage.DELAY:
                self._value = 0
                self._priority = 4 + self._value
                return True

            case _EnvelopeStage.ATTACK:
                self._value = self._attack_slope * (
                    current_time - self._attack_start_time
                )
                self._priority = 3 + self._value
                return True

            case _EnvelopeStage.HOLD:
                self._value = 1
                self._priority = 2 + self._value
                return True

            case _EnvelopeStage.DECAY:
                self._value = max(
                    _SoundFontMath.exp_cutoff(
                        self._decay_slope * (current_time - self._decay_start_time)
                    ),
                    self._sustain_level,
                )
                self._priority = 1 + self._value
                return self._value > _SoundFontMath.non_audible()

            case _EnvelopeStage.RELEASE:
                self._value = self._release_level * _SoundFontMath.exp_cutoff(
                    self._release_slope * (current_time - self._release_start_time)
                )
                self._priority = self._value
                return self._value > _SoundFontMath.non_audible()

    @property
    def value(self) -> float:
        return self._value

    @property
    def priority(self) -> float:
        return self._priority


class _ModulationEnvelope:
    _synthesizer: "Synthesizer"

    _attack_slope: float
    _decay_slope: float
    _release_slope: float

    _attack_start_time: float
    _hold_start_time: float
    _decay_start_time: float

    _decay_end_time: float
    _release_end_time: float

    _sustain_level: float
    _release_level: float

    _processed_sample_count: int
    _stage: _EnvelopeStage
    _value: float

    def __init__(self, synthesizer: "Synthesizer") -> None:
        self._synthesizer = synthesizer

    def start(
        self,
        delay: float,
        attack: float,
        hold: float,
        decay: float,
        sustain: float,
        release: float,
    ) -> None:
        self._attack_slope = 1 / attack
        self._decay_slope = 1 / decay
        self._release_slope = 1 / release

        self._attack_start_time = delay
        self._hold_start_time = self._attack_start_time + attack
        self._decay_start_time = self._hold_start_time + hold

        self._decay_end_time = self._decay_start_time + decay
        self._release_end_time = release

        self._sustain_level = _SoundFontMath.clamp(sustain, 0, 1)
        self._release_level = 0

        self._processed_sample_count = 0
        self._stage = _EnvelopeStage.DELAY
        self._value = 0

        self.process(0)

    def release(self) -> None:
        self._stage = _EnvelopeStage.RELEASE
        self._release_end_time += (
            float(self._processed_sample_count) / self._synthesizer.sample_rate
        )
        self._release_level = self._value

    def process(self, sample_count: int) -> bool:
        self._processed_sample_count += sample_count

        current_time = (
            float(self._processed_sample_count) / self._synthesizer.sample_rate
        )

        while self._stage <= _EnvelopeStage.HOLD:
            end_time: float

            match self._stage:
                case _EnvelopeStage.DELAY:
                    end_time = self._attack_start_time

                case _EnvelopeStage.ATTACK:
                    end_time = self._hold_start_time

                case _EnvelopeStage.HOLD:
                    end_time = self._decay_start_time

                case _:
                    raise Exception("Invalid envelope stage.")

            if current_time < end_time:
                break
            else:
                self._stage = _EnvelopeStage(self._stage.value + 1)

        match self._stage:
            case _EnvelopeStage.DELAY:
                self._value = 0
                return True

            case _EnvelopeStage.ATTACK:
                self._value = self._attack_slope * (
                    current_time - self._attack_start_time
                )
                return True

            case _EnvelopeStage.HOLD:
                self._value = 1
                return True

            case _EnvelopeStage.DECAY:
                self._value = max(
                    self._decay_slope * (self._decay_end_time - current_time),
                    self._sustain_level,
                )
                return self._value > _SoundFontMath.non_audible()

            case _EnvelopeStage.RELEASE:
                self._value = max(
                    self._release_level
                    * self._release_slope
                    * (self._release_end_time - current_time),
                    0,
                )
                return self._value > _SoundFontMath.non_audible()

    @property
    def value(self) -> float:
        return self._value


class _Lfo:
    _synthesizer: "Synthesizer"

    _active: bool

    _delay: float
    _period: float

    _processed_sample_count: int
    _value: float

    def __init__(self, synthesizer: "Synthesizer") -> None:
        self._synthesizer = synthesizer

    def start(self, delay: float, frequency: float) -> None:
        if frequency > 1.0e-3:
            self._active = True

            self._delay = delay
            self._period = 1.0 / frequency

            self._processed_sample_count = 0
            self._value = 0

        else:
            self._active = False
            self._value = 0

    def process(self) -> None:
        if not self._active:
            return

        self._processed_sample_count += self._synthesizer.block_size

        current_time = (
            float(self._processed_sample_count) / self._synthesizer.sample_rate
        )

        if current_time < self._delay:
            self._value = 0

        else:
            phase = ((current_time - self._delay) % self._period) / self._period
            if phase < 0.25:
                self._value = 4 * phase
            elif phase < 0.75:
                self._value = 4 * (0.5 - phase)
            else:
                self._value = 4 * (phase - 1.0)

    @property
    def value(self) -> float:
        return self._value


class _RegionEx:
    @staticmethod
    def start_oscillator(
        oscillator: _Oscillator, data: Sequence[float], region: _RegionPair
    ) -> None:
        sample_rate = region.instrument.sample.sample_rate
        loop_mode = region.sample_modes
        start = region.sample_start
        end = region.sample_end
        start_loop = region.sample_start_loop
        end_Loop = region.sample_end_loop
        root_key = region.root_key
        coarse_tune = region.coarse_tune
        fine_tune = region.fine_tune
        scale_tuning = region.scale_tuning

        oscillator.start(
            data,
            loop_mode,
            sample_rate,
            start,
            end,
            start_loop,
            end_Loop,
            root_key,
            coarse_tune,
            fine_tune,
            scale_tuning,
        )

    @staticmethod
    def start_volume_envelope(
        envelope: _VolumeEnvelope, region: _RegionPair, key: int, velocity: int
    ) -> None:
        # If the release time is shorter than 10 ms, it will be clamped to 10 ms to avoid pop noise.

        delay = region.delay_volume_envelope
        attack = region.attack_volume_envelope
        hold = (
            region.hold_volume_envelope
            * _SoundFontMath.key_number_to_multiplying_factor(
                region.key_number_to_volume_envelope_hold, key
            )
        )
        decay = (
            region.decay_volume_envelope
            * _SoundFontMath.key_number_to_multiplying_factor(
                region.key_number_to_volume_envelope_decay, key
            )
        )
        sustain = _SoundFontMath.decibels_to_linear(-region.sustain_volume_envelope)
        release = max(region.release_volume_envelope, 0.01)

        envelope.start(delay, attack, hold, decay, sustain, release)

    @staticmethod
    def start_modulation_envelope(
        envelope: _ModulationEnvelope, region: _RegionPair, key: int, velocity: int
    ) -> None:
        # According to the implementation of TinySoundFont, the attack time should be adjusted by the velocity.

        delay = region.delay_modulation_envelope
        attack = region.attack_modulation_envelope * ((145 - velocity) / 144.0)
        hold = (
            region.hold_modulation_envelope
            * _SoundFontMath.key_number_to_multiplying_factor(
                region.key_number_to_modulation_envelope_hold, key
            )
        )
        decay = (
            region.decay_modulation_envelope
            * _SoundFontMath.key_number_to_multiplying_factor(
                region.key_number_to_modulation_envelope_decay, key
            )
        )
        sustain = 1.0 - region.sustain_modulation_envelope / 100.0
        release = region.release_modulation_envelope

        envelope.start(delay, attack, hold, decay, sustain, release)

    @staticmethod
    def start_vibrato(lfo: _Lfo, region: _RegionPair, key: int, velocity: int) -> None:
        lfo.start(region.delay_vibrato_lfo, region.frequency_vibrato_lfo)

    @staticmethod
    def start_modulation(
        lfo: _Lfo, region: _RegionPair, key: int, velocity: int
    ) -> None:
        lfo.start(region.delay_modulation_lfo, region.frequency_modulation_lfo)


class _BiQuadFilter:
    _synthesizer: "Synthesizer"

    _resonance_peak_offset: float

    _active: bool

    _a0: float
    _a1: float
    _a2: float
    _a3: float
    _a4: float

    _x1: float
    _x2: float
    _y1: float
    _y2: float

    def __init__(self, synthesizer: "Synthesizer") -> None:
        self._synthesizer = synthesizer
        self._resonance_peak_offset = 1.0 - 1.0 / math.sqrt(2.0)

    def clear_buffer(self) -> None:
        self._x1 = 0
        self._x2 = 0
        self._y1 = 0
        self._y2 = 0

    def set_low_pass_filter(self, cutoff_frequency: float, resonance: float) -> None:
        if cutoff_frequency < 0.499 * self._synthesizer.sample_rate:
            self._active = True

            # This equation gives the Q value which makes the desired resonance peak.
            # The error of the resultant peak height is less than 3%.
            q = resonance - self._resonance_peak_offset / (1 + 6 * (resonance - 1))

            w = 2 * math.pi * cutoff_frequency / self._synthesizer.sample_rate
            cosw = math.cos(w)
            alpha = math.sin(w) / (2 * q)

            b0 = (1 - cosw) / 2
            b1 = 1 - cosw
            b2 = (1 - cosw) / 2
            a0 = 1 + alpha
            a1 = -2 * cosw
            a2 = 1 - alpha

            self.set_coefficients(a0, a1, a2, b0, b1, b2)

        else:
            self._active = False

    def process(self, block: MutableSequence[float]) -> None:
        if self._active:
            for t in range(len(block)):
                input = block[t]
                output = (
                    self._a0 * input
                    + self._a1 * self._x1
                    + self._a2 * self._x2
                    - self._a3 * self._y1
                    - self._a4 * self._y2
                )

                self._x2 = self._x1
                self._x1 = input
                self._y2 = self._y1
                self._y1 = output

                block[t] = output

        else:
            self._x2 = block[len(block) - 2]
            self._x1 = block[len(block) - 1]
            self._y2 = self._x2
            self._y1 = self._x1

    def set_coefficients(
        self, a0: float, a1: float, a2: float, b0: float, b1: float, b2: float
    ) -> None:
        self._a0 = b0 / a0
        self._a1 = b1 / a0
        self._a2 = b2 / a0
        self._a3 = a1 / a0
        self._a4 = a2 / a0


class _Channel:
    _synthesizer: "Synthesizer"
    _is_percussion_channel: bool

    _bank_number: int
    _patch_number: int

    _modulation: int
    _volume: int
    _pan: int
    _expression: int
    _hold_pedal: bool

    _reverb_send: int
    _chorus_send: int

    _rpn: int
    _pitch_bend_range: int
    _coarse_tune: int
    _fine_tune: int

    _pitch_bend: float

    def __init__(self, synthesizer: "Synthesizer", is_percussion_channel: bool) -> None:
        self._synthesizer = synthesizer
        self._is_percussion_channel = is_percussion_channel

        self.reset()

    def reset(self) -> None:
        self._bank_number = 128 if self._is_percussion_channel else 0
        self._patch_number = 0

        self._modulation = 0
        self._volume = 100 << 7
        self._pan = 64 << 7
        self._expression = 127 << 7
        self._hold_pedal = False

        self._reverb_send = 40
        self._chorus_send = 0

        self._rpn = -1
        self._pitch_bend_range = 2 << 7
        self._coarse_tune = 0
        self._fine_tune = 8192

        self._pitch_bend = 0

    def reset_all_controllers(self) -> None:
        self._modulation = 0
        self._expression = 127 << 7
        self._hold_pedal = False

        self._rpn = -1

        self._pitch_bend = 0

    def set_bank(self, value: int) -> None:
        self._bank_number = value

        if self._is_percussion_channel:
            self._bank_number += 128

    def set_patch(self, value: int) -> None:
        self._patch_number = value

    def set_modulation_coarse(self, value: int) -> None:
        self._modulation = (self._modulation & 0x7F) | (value << 7)

    def set_modulation_fine(self, value: int) -> None:
        self._modulation = (self._modulation & 0xFF80) | value

    def set_volume_coarse(self, value: int) -> None:
        self._volume = (self._volume & 0x7F) | (value << 7)

    def set_volume_fine(self, value: int) -> None:
        self._volume = (self._volume & 0xFF80) | value

    def set_pan_coarse(self, value: int) -> None:
        self._pan = (self._pan & 0x7F) | (value << 7)

    def set_pan_fine(self, value: int) -> None:
        self._pan = (self._pan & 0xFF80) | value

    def set_expression_coarse(self, value: int) -> None:
        self._expression = (self._expression & 0x7F) | (value << 7)

    def set_expression_fine(self, value: int) -> None:
        self._expression = (self._expression & 0xFF80) | value

    def set_hold_pedal(self, value: int) -> None:
        self._hold_pedal = value >= 64

    def set_reverb_send(self, value: int) -> None:
        self._reverb_send = value

    def set_chorus_send(self, value: int) -> None:
        self._chorus_send = value

    def set_rpn_coarse(self, value: int) -> None:
        self._rpn = (self._rpn & 0x7F) | (value << 7)

    def set_rpn_fine(self, value: int) -> None:
        self._vrpn = (self._rpn & 0xFF80) | value

    def data_entry_coarse(self, value: int) -> None:
        match self._rpn:
            case 0:
                self._pitch_bend_range = (self._pitch_bend_range & 0x7F) | (value << 7)

            case 1:
                self._fine_tune = (self._fine_tune & 0x7F) | (value << 7)

            case 2:
                self._coarse_tune = value - 64

            case _:
                pass

    def data_entry_fine(self, value: int) -> None:
        match self._rpn:
            case 0:
                self._pitch_bend_range = (self._pitch_bend_range & 0xFF80) | value

            case 1:
                self._fine_tune = (self._fine_tune & 0xFF80) | value

            case _:
                pass

    def set_pitch_bend(self, value1: int, value2: int) -> None:
        self._pitch_bend = (1.0 / 8192.0) * ((value1 | (value2 << 7)) - 8192)

    @property
    def is_percussion_channel(self) -> bool:
        return self._is_percussion_channel

    @property
    def bank_number(self) -> int:
        return self._bank_number

    @property
    def patch_number(self) -> int:
        return self._patch_number

    @property
    def modulation(self) -> float:
        return (50.0 / 16383.0) * self._modulation

    @property
    def volume(self) -> float:
        return (1.0 / 16383.0) * self._volume

    @property
    def pan(self) -> float:
        return (100.0 / 16383.0) * self._pan - 50.0

    @property
    def expression(self) -> float:
        return (1.0 / 16383.0) * self._expression

    @property
    def hold_pedal(self) -> float:
        return self._hold_pedal

    @property
    def reverb_send(self) -> float:
        return (1.0 / 127.0) * self._reverb_send

    @property
    def chorus_send(self) -> float:
        return (1.0 / 127.0) * self._chorus_send

    @property
    def pitch_bend_range(self) -> float:
        return (self._pitch_bend_range >> 7) + 0.01 * (self._pitch_bend_range & 0x7F)

    @property
    def tune(self) -> float:
        return self._coarse_tune + (1.0 / 8192.0) * (self._fine_tune - 8192)

    @property
    def pitch_bend(self) -> float:
        return self.pitch_bend_range * self._pitch_bend


class _VoiceState(IntEnum):
    PLAYING = 0
    RELEASE_REQUESTED = 1
    RELEASED = 2


class _Voice:
    _synthesizer: "Synthesizer"

    _volEnv: _VolumeEnvelope
    _modEnv: _ModulationEnvelope

    _vibLfo: _Lfo
    _modLfo: _Lfo

    _oscillator: _Oscillator
    _filter: _BiQuadFilter

    _block: MutableSequence[float]

    # A sudden change in the mix gain will cause pop noise.
    # To avoid this, we save the mix gain of the previous block,
    # and smooth out the gain if the gap between the current and previous gain is too large.
    # The actual smoothing process is done in the WriteBlock method of the Synthesizer class.

    _previous_mix_gain_left: float
    _previous_mix_gain_right: float
    _current_mix_gain_left: float
    _current_mix_gain_right: float

    _previous_reverb_send: float
    _previous_chorus_send: float
    _current_reverb_send: float
    _current_chorus_send: float

    _exclusive_class: int
    _channel: int
    _key: int
    _velocity: int

    _note_gain: float

    _cutoff: float
    _resonance: float

    _vib_lfo_to_pitch: float
    _mod_lfo_to_pitch: float
    _mod_env_to_pitch: float

    _mod_lfo_to_cutoff: int
    _mod_env_to_cutoff: int
    _dynamic_cutoff: bool

    _mod_lfo_to_volume: float
    _dynamic_volume: bool

    _instrument_pan: float
    _instrument_reverb: float
    _instrument_chorus: float

    # Some instruments require fast cutoff change, which can cause pop noise.
    # This is used to smooth out the cutoff frequency.
    _smoothed_cutoff: float

    _voice_state: _VoiceState
    _voice_length: int

    def __init__(self, synthesizer: "Synthesizer") -> None:
        self._synthesizer = synthesizer

        self._vol_env = _VolumeEnvelope(synthesizer)
        self._mod_env = _ModulationEnvelope(synthesizer)

        self._vib_lfo = _Lfo(synthesizer)
        self._mod_lfo = _Lfo(synthesizer)

        self._oscillator = _Oscillator(synthesizer)
        self._filter = _BiQuadFilter(synthesizer)

        self._block = create_buffer(synthesizer.block_size)

        self._current_mix_gain_left = 0
        self._current_mix_gain_right = 0
        self._current_reverb_send = 0
        self._current_chorus_send = 0

    def start(self, region: _RegionPair, channel: int, key: int, velocity: int) -> None:
        self._exclusive_class = region.exclusive_class
        self._channel = channel
        self._key = key
        self._velocity = velocity

        if velocity > 0:
            # According to the Polyphone's implementation, the initial attenuation should be reduced to 40%.
            # I'm not sure why, but this indeed improves the loudness variability.
            sample_attenuation = 0.4 * region.initial_attenuation
            filter_attenuation = 0.5 * region.initial_filter_q
            decibels = (
                2 * _SoundFontMath.linear_to_decibels(velocity / 127.0)
                - sample_attenuation
                - filter_attenuation
            )
            self._note_gain = _SoundFontMath.decibels_to_linear(decibels)

        else:
            self._note_gain = 0

        self._cutoff = region.initial_filter_cutoff_frequency
        self._resonance = _SoundFontMath.decibels_to_linear(region.initial_filter_q)

        self._vib_lfo_to_pitch = 0.01 * region.vibrato_lfo_to_pitch
        self._mod_lfo_to_pitch = 0.01 * region.modulation_lfo_to_pitch
        self._mod_env_to_pitch = 0.01 * region.modulation_envelope_to_pitch

        self._mod_lfo_to_cutoff = region.modulation_lfo_to_filter_cutoff_frequency
        self._mod_env_to_cutoff = region.modulation_envelope_to_filter_cutoff_frequency
        self._dynamic_cutoff = (
            self._mod_lfo_to_cutoff != 0 or self._mod_env_to_cutoff != 0
        )

        self._mod_lfo_to_volume = region.modulation_lfo_to_volume
        self._dynamic_volume = self._mod_lfo_to_volume > 0.05

        self._instrument_pan = _SoundFontMath.clamp(region.pan, -50, 50)
        self._instrument_reverb = 0.01 * region.reverb_effects_send
        self._instrument_chorus = 0.01 * region.chorus_effects_send

        _RegionEx.start_volume_envelope(self._vol_env, region, key, velocity)
        _RegionEx.start_modulation_envelope(self._mod_env, region, key, velocity)
        _RegionEx.start_vibrato(self._vib_lfo, region, key, velocity)
        _RegionEx.start_modulation(self._mod_lfo, region, key, velocity)
        _RegionEx.start_oscillator(
            self._oscillator, self._synthesizer.sound_font.wave_data, region
        )
        self._filter.clear_buffer()
        self._filter.set_low_pass_filter(self._cutoff, self._resonance)

        self._smoothed_cutoff = self._cutoff

        self._voice_state = _VoiceState.PLAYING
        self._voice_length = 0

    def end(self) -> None:
        if self._voice_state == _VoiceState.PLAYING:
            self._voice_state = _VoiceState.RELEASE_REQUESTED

    def kill(self) -> None:
        self._note_gain = 0

    def process(self) -> bool:
        if self._note_gain < _SoundFontMath.non_audible():
            return False

        channel_info = self._synthesizer._channels[self._channel]  # type: ignore

        self.release_if_necessary(channel_info)

        if not self._vol_env.process(self._synthesizer.block_size):
            return False

        self._mod_env.process(self._synthesizer.block_size)
        self._vib_lfo.process()
        self._mod_lfo.process()

        vib_pitch_change = (
            0.01 * channel_info.modulation + self._vib_lfo_to_pitch
        ) * self._vib_lfo.value
        mod_pitch_change = (
            self._mod_lfo_to_pitch * self._mod_lfo.value
            + self._mod_env_to_pitch * self._mod_env.value
        )
        channel_pitch_change = channel_info.tune + channel_info.pitch_bend
        pitch = self._key + vib_pitch_change + mod_pitch_change + channel_pitch_change
        if not self._oscillator.process(self._block, pitch):
            return False

        if self._dynamic_cutoff:
            cents = (
                self._mod_lfo_to_cutoff * self._mod_lfo.value
                + self._mod_env_to_cutoff * self._mod_env.value
            )
            factor = _SoundFontMath.cents_to_multiplying_factor(cents)
            new_cutoff = factor * self._cutoff

            # The cutoff change is limited within x0.5 and x2 to reduce pop noise.
            lower_limit = 0.5 * self._smoothed_cutoff
            upper_limit = 2.0 * self._smoothed_cutoff
            if new_cutoff < lower_limit:
                self._smoothed_cutoff = lower_limit
            elif new_cutoff > upper_limit:
                self._smoothed_cutoff = upper_limit
            else:
                self._smoothed_cutoff = new_cutoff

            self._filter.set_low_pass_filter(self._smoothed_cutoff, self._resonance)

        self._filter.process(self._block)

        self._previous_mix_gain_left = self._current_mix_gain_left
        self._previous_mix_gain_right = self._current_mix_gain_right
        self._previous_reverb_send = self._current_reverb_send
        self._previous_chorus_send = self._current_chorus_send

        # According to the GM spec, the following value should be squared.
        ve = channel_info.volume * channel_info.expression
        channel_gain = ve * ve

        mix_gain = self._note_gain * channel_gain * self._vol_env.value
        if self._dynamic_volume:
            decibels = self._mod_lfo_to_volume * self._mod_lfo.value
            mix_gain *= _SoundFontMath.decibels_to_linear(decibels)

        angle = (math.pi / 200.0) * (channel_info.pan + self._instrument_pan + 50.0)
        if angle <= 0:
            self._current_mix_gain_left = mix_gain
            self._current_mix_gain_right = 0
        elif angle >= _SoundFontMath.half_pi():
            self._current_mix_gain_left = 0
            self._current_mix_gain_right = mix_gain
        else:
            self._current_mix_gain_left = mix_gain * math.cos(angle)
            self._current_mix_gain_right = mix_gain * math.sin(angle)

        self._current_reverb_send = _SoundFontMath.clamp(
            channel_info.reverb_send + self._instrument_reverb, 0, 1
        )
        self._current_chorus_send = _SoundFontMath.clamp(
            channel_info.chorus_send + self._instrument_chorus, 0, 1
        )

        if self._voice_length == 0:
            self._previous_mix_gain_left = self._current_mix_gain_left
            self._previous_mix_gain_right = self._current_mix_gain_right
            self._previous_reverb_send = self._current_reverb_send
            self._previous_chorus_send = self._current_chorus_send

        self._voice_length += self._synthesizer.block_size

        return True

    def release_if_necessary(self, channel_info: _Channel) -> None:
        if self._voice_length < self._synthesizer._minimum_voice_duration:  # type: ignore
            return

        if (
            self._voice_state == _VoiceState.RELEASE_REQUESTED
            and not channel_info.hold_pedal
        ):
            self._vol_env.release()
            self._mod_env.release()
            self._oscillator.release()

            self._voice_state = _VoiceState.RELEASED

    @property
    def priority(self) -> float:
        if self._note_gain < _SoundFontMath.non_audible():
            return 0
        else:
            return self._vol_env.priority

    @property
    def block(self) -> Sequence[float]:
        return self._block

    @property
    def previous_mix_gain_left(self) -> float:
        return self._previous_mix_gain_left

    @property
    def previous_mix_gain_right(self) -> float:
        return self._previous_mix_gain_right

    @property
    def current_mix_gain_left(self) -> float:
        return self._current_mix_gain_left

    @property
    def current_mix_gain_right(self) -> float:
        return self._current_mix_gain_right

    @property
    def previous_reverb_send(self) -> float:
        return self._previous_reverb_send

    @property
    def previous_chorus_send(self) -> float:
        return self._previous_chorus_send

    @property
    def current_reverb_send(self) -> float:
        return self._current_reverb_send

    @property
    def current_chorus_send(self) -> float:
        return self._current_chorus_send

    @property
    def exclusive_class(self) -> int:
        return self._exclusive_class

    @property
    def channel(self) -> int:
        return self._channel

    @property
    def key(self) -> int:
        return self._key

    @property
    def velocity(self) -> int:
        return self._velocity

    @property
    def voice_length(self) -> int:
        return self._voice_length


class _VoiceCollection:
    _synthesizer: "Synthesizer"

    _voices: MutableSequence[_Voice]

    _active_voice_count: int

    def __init__(self, synthesizer: "Synthesizer", max_active_voice_count: int) -> None:
        self._synthesizer = synthesizer

        self._voices = list[_Voice]()
        for _ in range(max_active_voice_count):
            self._voices.append(_Voice(synthesizer))

        self._active_voice_count = 0

    def request_new(self, region: InstrumentRegion, channel: int) -> _Voice:
        # If an exclusive class is assigned to the region, find a voice with the same class.
        # If found, reuse it to avoid playing multiple voices with the same class at a time.
        exclusive_class = region.exclusive_class

        if exclusive_class != 0:
            for i in range(self._active_voice_count):
                voice = self._voices[i]
                if (
                    voice.exclusive_class == exclusive_class
                    and voice.channel == channel
                ):
                    return voice

        # If the number of active voices is less than the limit, use a free one.
        if self._active_voice_count < len(self._voices):
            free = self._voices[self._active_voice_count]
            self._active_voice_count += 1
            return free

        # Too many active voices...
        # Find one which has the lowest priority.
        candidate = self._voices[0]
        lowest_priority = 1000000.0

        for i in range(self._active_voice_count):
            voice = self._voices[i]
            priority = voice.priority

            if priority < lowest_priority:
                lowest_priority = priority
                candidate = voice

            elif priority == lowest_priority:
                # Same priority...
                # The older one should be more suitable for reuse.
                if voice.voice_length > candidate.voice_length:
                    candidate = voice

        return candidate

    def process(self) -> None:
        i = 0

        while True:
            if i == self._active_voice_count:
                return

            if self._voices[i].process():
                i += 1
            else:
                self._active_voice_count -= 1

                tmp = self._voices[i]
                self._voices[i] = self._voices[self._active_voice_count]
                self._voices[self._active_voice_count] = tmp

    def clear(self) -> None:
        self._active_voice_count = 0

    @property
    def active_voice_count(self) -> int:
        return self._active_voice_count


class SynthesizerSettings:
    _DEFAULT_BLOCK_SIZE = 64
    _DEFAULT_MAXIMUM_POLYPHONY = 64
    _DEFAULT_ENABLE_REVERB_AND_CHORUS = True

    _sample_rate: int
    _block_size: int
    _maximum_polyphony: int
    _enable_reverb_and_chorus: bool

    def __init__(self, sample_rate: int) -> None:
        SynthesizerSettings._check_sample_rate(sample_rate)

        self._sample_rate = sample_rate
        self._block_size = SynthesizerSettings._DEFAULT_BLOCK_SIZE
        self._maximum_polyphony = SynthesizerSettings._DEFAULT_MAXIMUM_POLYPHONY
        self._enable_reverb_and_chorus = (
            SynthesizerSettings._DEFAULT_ENABLE_REVERB_AND_CHORUS
        )

    @staticmethod
    def _check_sample_rate(value: int) -> None:
        if not (16000 <= value and value <= 192000):
            raise Exception("The sample rate must be between 16000 and 192000.")

    @staticmethod
    def _check_block_size(value: int) -> None:
        if not (8 <= value and value <= 1024):
            raise Exception("The block size must be between 8 and 1024.")

    @staticmethod
    def _check_maximum_polyphony(value: int) -> None:
        if not (8 <= value and value <= 256):
            raise Exception(
                "The maximum number of polyphony must be between 8 and 256."
            )

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @sample_rate.setter
    def sample_rate(self, value: int) -> None:
        SynthesizerSettings._check_sample_rate(value)
        self._sample_rate = value

    @property
    def block_size(self) -> int:
        return self._block_size

    @block_size.setter
    def block_size(self, value: int) -> None:
        SynthesizerSettings._check_block_size(value)
        self._block_size = value

    @property
    def maximum_polyphony(self) -> int:
        return self._maximum_polyphony

    @maximum_polyphony.setter
    def maximum_polyphony(self, value: int) -> None:
        SynthesizerSettings._check_maximum_polyphony(value)
        self._maximum_polyphony = value

    @property
    def enable_reverb_and_chorus(self) -> bool:
        return self._enable_reverb_and_chorus

    @enable_reverb_and_chorus.setter
    def enable_reverb_and_chorus(self, value: bool) -> None:
        self._enable_reverb_and_chorus = value


class Synthesizer:
    _CHANNEL_COUNT = 16
    _PERCUSSION_CHANNEL = 9

    _sound_font: SoundFont
    _sample_rate: int
    _block_size: int
    _maximum_polyphony: int
    _enable_reverb_and_chorus: bool

    _minimum_voice_duration: int

    _preset_lookup: dict[int, Preset]
    _default_preset: Preset

    _channels: list[_Channel]

    _voices: _VoiceCollection

    _block_left: MutableSequence[float]
    _block_right: MutableSequence[float]

    _inverse_block_size: float

    _block_read: int

    _master_volume: float

    def __init__(self, sound_font: SoundFont, settings: SynthesizerSettings) -> None:
        self._sound_font = sound_font
        self._sample_rate = settings.sample_rate
        self._block_size = settings.block_size
        self._maximum_polyphony = settings.maximum_polyphony
        self._enable_reverb_and_chorus = settings.enable_reverb_and_chorus

        self._minimum_voice_duration = int(self._sample_rate / 500)

        self._preset_lookup = dict[int, Preset]()

        min_preset_id = 10000000000
        for preset in self._sound_font.presets:
            # The preset ID is Int32, where the upper 16 bits represent the bank number
            # and the lower 16 bits represent the patch number.
            # This ID is used to search for presets by the combination of bank number
            # and patch number.
            preset_id = (preset.bank_number << 16) | preset.patch_number
            self._preset_lookup[preset_id] = preset

            # The preset with the minimum ID number will be default.
            # If the SoundFont is GM compatible, the piano will be chosen.
            if preset_id < min_preset_id:
                self._default_preset = preset
                min_preset_id = preset_id

        self._channels = list[_Channel]()
        for i in range(Synthesizer._CHANNEL_COUNT):
            self._channels.append(_Channel(self, i == Synthesizer._PERCUSSION_CHANNEL))

        self._voices = _VoiceCollection(self, self._maximum_polyphony)

        self._block_left = create_buffer(self._block_size)
        self._block_right = create_buffer(self._block_size)

        self._inverse_block_size = 1.0 / self._block_size

        self._block_read = self._block_size

        self._master_volume = 0.5

    def process_midi_message(
        self, channel: int, command: int, data1: int, data2: int
    ) -> None:
        if not (0 <= channel and channel < len(self._channels)):
            return

        channel_info = self._channels[channel]

        match command:
            case 0x80:  # Note Off
                self.note_off(channel, data1)

            case 0x90:  # Note On
                self.note_on(channel, data1, data2)

            case 0xB0:  # Controller
                match data1:
                    case 0x00:  # Bank Selection
                        channel_info.set_bank(data2)

                    case 0x01:  # Modulation Coarse
                        channel_info.set_modulation_coarse(data2)

                    case 0x21:  # Modulation Fine
                        channel_info.set_modulation_fine(data2)

                    case 0x06:  # Data Entry Coarse
                        channel_info.data_entry_coarse(data2)

                    case 0x26:  # Data Entry Fine
                        channel_info.data_entry_fine(data2)

                    case 0x07:  # Channel Volume Coarse
                        channel_info.set_volume_coarse(data2)

                    case 0x27:  # Channel Volume Fine
                        channel_info.set_volume_fine(data2)

                    case 0x0A:  # Pan Coarse
                        channel_info.set_pan_coarse(data2)

                    case 0x2A:  # Pan Fine
                        channel_info.set_pan_fine(data2)

                    case 0x0B:  # Expression Coarse
                        channel_info.set_expression_coarse(data2)

                    case 0x2B:  # Expression Fine
                        channel_info.set_expression_fine(data2)

                    case 0x40:  # Hold Pedal
                        channel_info.set_hold_pedal(data2)

                    case 0x5B:  # Reverb Send
                        channel_info.set_reverb_send(data2)

                    case 0x5D:  # Chorus Send
                        channel_info.set_chorus_send(data2)

                    case 0x65:  # RPN Coarse
                        channel_info.set_rpn_coarse(data2)

                    case 0x64:  # RPN Fine
                        channel_info.set_rpn_fine(data2)

                    case 0x78:  # All Sound Off
                        self.note_off_all_channel(channel, True)

                    case 0x79:  # Reset All Controllers
                        self.reset_all_controllers_channel(channel)

                    case 0x7B:  # All Note Off
                        self.note_off_all_channel(channel, False)

                    case _:
                        pass

            case 0xC0:  # Program Change
                channel_info.set_patch(data1)

            case 0xE0:  # Pitch Bend
                channel_info.set_pitch_bend(data1, data2)

            case _:
                pass

    def note_off(self, channel: int, key: int) -> None:
        if not (0 <= channel and channel < len(self._channels)):
            return

        for i in range(self._voices.active_voice_count):
            voice = self._voices._voices[i]  # type: ignore
            if voice.channel == channel and voice.key == key:
                voice.end()

    def note_on(self, channel: int, key: int, velocity: int) -> None:
        if velocity == 0:
            self.note_off(channel, key)
            return

        if not (0 <= channel and channel < len(self._channels)):
            return

        channel_info = self._channels[channel]

        preset_id = (channel_info.bank_number << 16) | channel_info.patch_number

        preset = self._sound_font.presets[0]
        if preset_id in self._preset_lookup:
            preset = self._preset_lookup[preset_id]
        else:
            # Try fallback to the GM sound set.
            # Normally, the given patch number + the bank number 0 will work.
            # For drums (bank number >= 128), it seems to be better to select the standard set (128:0).
            gm_preset_id = (
                channel_info.patch_number
                if channel_info.bank_number < 128
                else (128 << 16)
            )
            if gm_preset_id in self._preset_lookup:
                preset = self._preset_lookup[gm_preset_id]
            else:
                # No corresponding preset was found. Use the default one...
                preset = self._default_preset

        for preset_region in preset.regions:
            if preset_region.contains(key, velocity):
                for instrument_region in preset_region.instrument.regions:
                    if instrument_region.contains(key, velocity):
                        region_pair = _RegionPair(preset_region, instrument_region)
                        voice = self._voices.request_new(instrument_region, channel)
                        voice.start(region_pair, channel, key, velocity)

    def note_off_all(self, immediate: bool) -> None:
        if immediate:
            self._voices.clear()
        else:
            for i in range(self._voices.active_voice_count):
                self._voices._voices[i].end()  # type: ignore

    def note_off_all_channel(self, channel: int, immediate: bool) -> None:
        if immediate:
            for i in range(self._voices.active_voice_count):
                if self._voices._voices[i].channel == channel:  # type: ignore
                    self._voices._voices[i].kill()  # type: ignore
        else:
            for i in range(self._voices.active_voice_count):
                if self._voices._voices[i].channel == channel:  # type: ignore
                    self._voices._voices[i].end()  # type: ignore

    def reset_all_controllers(self) -> None:
        for channel in self._channels:
            channel.reset_all_controllers()

    def reset_all_controllers_channel(self, channel: int) -> None:
        if not (0 <= channel and channel < len(self._channels)):
            return

        self._channels[channel].reset_all_controllers()

    def reset(self):
        self._voices.clear()

        for channel in self._channels:
            channel.reset()

        self._block_read = self._block_size

    def render(
        self,
        left: MutableSequence[float],
        right: MutableSequence[float],
        offset: Optional[int] = None,
        count: Optional[int] = None,
    ) -> None:
        if len(left) != len(right):
            raise Exception(
                "The output buffers for the left and right must be the same length."
            )

        if offset is None:
            offset = 0
        elif count is None:
            raise Exception("'count' must be set if 'offset' is set.")

        if count is None:
            count = len(left)

        wrote = 0

        while wrote < count:
            if self._block_read == self._block_size:
                self._render_block()
                self._block_read = 0

            src_rem = self._block_size - self._block_read
            dst_rem = count - wrote
            rem = min(src_rem, dst_rem)

            for t in range(rem):
                left[offset + wrote + t] = self._block_left[self._block_read + t]
                right[offset + wrote + t] = self._block_right[self._block_read + t]

            self._block_read += rem
            wrote += rem

    def _render_block(self) -> None:
        self._voices.process()

        for t in range(self._block_size):
            self._block_left[t] = 0
            self._block_right[t] = 0

        for i in range(self._voices.active_voice_count):
            voice = self._voices._voices[i]  # type: ignore

            previous_gain_left = self._master_volume * voice.previous_mix_gain_left
            current_gain_left = self._master_volume * voice.current_mix_gain_left
            self._write_block(
                previous_gain_left, current_gain_left, voice.block, self._block_left
            )
            previous_gain_right = self._master_volume * voice.previous_mix_gain_right
            current_gain_right = self._master_volume * voice.current_mix_gain_right
            self._write_block(
                previous_gain_right, current_gain_right, voice.block, self._block_right
            )

    def _write_block(
        self,
        previous_gain: float,
        current_gain: float,
        source: Sequence[float],
        destination: MutableSequence[float],
    ) -> None:
        if max(previous_gain, current_gain) < _SoundFontMath.non_audible():
            return

        if abs(current_gain - previous_gain) < 1.0e-3:
            _ArrayMath.multiply_add(current_gain, source, destination)

        else:
            step = self._inverse_block_size * (current_gain - previous_gain)
            _ArrayMath.multiply_add_slope(previous_gain, step, source, destination)

    @property
    def block_size(self) -> int:
        return self._block_size

    @property
    def maximum_polyphony(self) -> int:
        return self._maximum_polyphony

    @property
    def channel_count(self) -> int:
        return Synthesizer._CHANNEL_COUNT

    @property
    def percussion_channel(self) -> int:
        return Synthesizer._PERCUSSION_CHANNEL

    @property
    def sound_font(self) -> SoundFont:
        return self._sound_font

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def active_voice_count(self) -> int:
        return self._voices.active_voice_count

    @property
    def master_volume(self) -> float:
        return self._master_volume

    @master_volume.setter
    def master_volume(self, value: float) -> None:
        self._master_volume = value


class _MidiMessageType(IntEnum):
    NORMAL = 0
    TEMPO_CHANGE = 252
    END_OF_TRACK = 255


class _MidiMessage:
    _data: bytearray

    def __init__(self, channel: int, command: int, data1: int, data2: int) -> None:
        self._data = bytearray()
        self._data.append(channel & 0xFF)
        self._data.append(command & 0xFF)
        self._data.append(data1 & 0xFF)
        self._data.append(data2 & 0xFF)

    @staticmethod
    def common1(status: int, data1: int) -> "_MidiMessage":
        channel = status & 0x0F
        command = status & 0xF0
        data2 = 0

        return _MidiMessage(channel, command, data1, data2)

    @staticmethod
    def common2(status: int, data1: int, data2: int) -> "_MidiMessage":
        channel = status & 0x0F
        command = status & 0xF0

        return _MidiMessage(channel, command, data1, data2)

    @staticmethod
    def tempo_change(tempo: int) -> "_MidiMessage":
        command = tempo >> 16
        data1 = tempo >> 8
        data2 = tempo

        return _MidiMessage(_MidiMessageType.TEMPO_CHANGE, command, data1, data2)

    @staticmethod
    def end_of_track() -> "_MidiMessage":
        return _MidiMessage(_MidiMessageType.END_OF_TRACK, 0, 0, 0)

    @property
    def type(self) -> _MidiMessageType:
        match self.channel:
            case int(_MidiMessageType.TEMPO_CHANGE):
                return _MidiMessageType.TEMPO_CHANGE

            case int(_MidiMessageType.END_OF_TRACK):
                return _MidiMessageType.END_OF_TRACK

            case _:
                return _MidiMessageType.NORMAL

    @property
    def channel(self) -> int:
        return self._data[0]

    @property
    def command(self) -> int:
        return self._data[1]

    @property
    def data1(self) -> int:
        return self._data[2]

    @property
    def data2(self) -> int:
        return self._data[3]

    @property
    def tempo(self) -> float:
        return 60000000.0 / ((self.command << 16) | (self.data1 << 8) | self.data2)


class MidiFile:
    _track_count: int
    _resolution: int

    _messages: Sequence[_MidiMessage]
    _times: Sequence[float]

    def __init__(self, reader: BufferedIOBase) -> None:
        chunk_type = _BinaryReaderEx.read_four_cc(reader)
        if chunk_type != "MThd":
            raise Exception(
                "The chunk type must be 'MThd', but was '" + chunk_type + "'."
            )

        size = _BinaryReaderEx.read_int32_big_endian(reader)
        if size != 6:
            raise Exception("The MThd chunk has invalid data.")

        format = _BinaryReaderEx.read_int16_big_endian(reader)
        if not (format == 0 or format == 1):
            raise Exception("The format " + str(format) + " is not supported.")

        self._track_count = _BinaryReaderEx.read_int16_big_endian(reader)
        self._resolution = _BinaryReaderEx.read_int16_big_endian(reader)

        message_lists = list[list[_MidiMessage]]()
        tick_lists = list[list[int]]()

        for _ in range(self._track_count):
            message_list, tick_list = MidiFile._read_track(reader)
            message_lists.append(message_list)
            tick_lists.append(tick_list)

        messages, times = MidiFile._merge_tracks(
            message_lists, tick_lists, self._resolution
        )

        self._messages = messages
        self._times = times

    @classmethod
    def from_file(cls, file_path: str) -> "MidiFile":
        with open(file_path, "rb") as f:
            return cls(f)

    @staticmethod
    def _read_track(reader: BufferedIOBase) -> tuple[list[_MidiMessage], list[int]]:
        chunk_type = _BinaryReaderEx.read_four_cc(reader)
        if chunk_type != "MTrk":
            raise Exception(
                "The chunk type must be 'MTrk', but was '" + chunk_type + "'."
            )

        end = _BinaryReaderEx.read_int32_big_endian(reader)
        end += reader.tell()

        messages = list[_MidiMessage]()
        ticks = list[int]()

        tick = 0
        last_status = 0

        while True:
            delta = _BinaryReaderEx.read_int_variable_length(reader)
            first = _BinaryReaderEx.read_uint8(reader)

            tick += delta

            if (first & 128) == 0:
                command = last_status & 0xF0
                if command == 0xC0 or command == 0xD0:
                    messages.append(_MidiMessage.common1(last_status, first))
                    ticks.append(tick)
                else:
                    data2 = _BinaryReaderEx.read_uint8(reader)
                    messages.append(_MidiMessage.common2(last_status, first, data2))
                    ticks.append(tick)

                continue

            match first:
                case 0xF0:  # System Exclusive
                    MidiFile.discard_data(reader)

                case 0xF7:  # System Exclusive
                    MidiFile.discard_data(reader)

                case 0xFF:  # Meta Event
                    match _BinaryReaderEx.read_uint8(reader):
                        case 0x2F:  # End of Track
                            _BinaryReaderEx.read_uint8(reader)
                            messages.append(_MidiMessage.end_of_track())
                            ticks.append(tick)

                            # Some MIDI files may have events inserted after the EOT.
                            # Such events should be ignored.
                            if reader.tell() < end:
                                reader.seek(end, io.SEEK_SET)

                            return messages, ticks
                        case 0x51:  # Tempo
                            messages.append(
                                _MidiMessage.tempo_change(MidiFile.read_tempo(reader))
                            )
                            ticks.append(tick)
                        case _:
                            MidiFile.discard_data(reader)

                case _:
                    command = first & 0xF0
                    if command == 0xC0 or command == 0xD0:
                        data1 = _BinaryReaderEx.read_uint8(reader)
                        messages.append(_MidiMessage.common1(first, data1))
                        ticks.append(tick)
                    else:
                        data1 = _BinaryReaderEx.read_uint8(reader)
                        data2 = _BinaryReaderEx.read_uint8(reader)
                        messages.append(_MidiMessage.common2(first, data1, data2))
                        ticks.append(tick)

            last_status = first

    @staticmethod
    def _merge_tracks(
        message_lists: list[list[_MidiMessage]],
        tick_lists: list[list[int]],
        resolution: int,
    ) -> tuple[list[_MidiMessage], list[float]]:
        merged_messages = list[_MidiMessage]()
        merged_times = list[float]()

        indices = list[int](itertools.repeat(0, len(message_lists)))

        current_tick: int = 0
        current_time: float = 0.0

        tempo: float = 120.0

        while True:
            min_tick = 10000000000
            min_index = -1

            for ch in range(len(tick_lists)):
                if indices[ch] < len(tick_lists[ch]):
                    tick = tick_lists[ch][indices[ch]]
                    if tick < min_tick:
                        min_tick = tick
                        min_index = ch

            if min_index == -1:
                break

            next_tick = tick_lists[min_index][indices[min_index]]
            delta_tick = next_tick - current_tick
            delta_time = 60.0 / (resolution * tempo) * delta_tick

            current_tick += delta_tick
            current_time += delta_time

            message = message_lists[min_index][indices[min_index]]
            if message.type == _MidiMessageType.TEMPO_CHANGE:
                tempo = message.tempo
            else:
                merged_messages.append(message)
                merged_times.append(current_time)

            indices[min_index] += 1

        return merged_messages, merged_times

    @staticmethod
    def read_tempo(reader: BufferedIOBase) -> int:
        size = _BinaryReaderEx.read_int_variable_length(reader)
        if size != 3:
            raise Exception("Failed to read the tempo value.")

        b1 = _BinaryReaderEx.read_uint8(reader)
        b2 = _BinaryReaderEx.read_uint8(reader)
        b3 = _BinaryReaderEx.read_uint8(reader)

        return (b1 << 16) | (b2 << 8) | b3

    @staticmethod
    def discard_data(reader: BufferedIOBase) -> None:
        size = _BinaryReaderEx.read_int_variable_length(reader)
        reader.seek(size, io.SEEK_CUR)

    @property
    def length(self) -> float:
        return self._times[-1]


class MidiFileSequencer:
    _synthesizer: Synthesizer

    _midi_file: Optional[MidiFile]
    _loop: bool

    _block_wrote: int

    _current_time: float
    _msg_index: int

    _block_left: MutableSequence[float]
    _block_right: MutableSequence[float]

    def __init__(self, synthesizer: Synthesizer) -> None:
        self._synthesizer = synthesizer

    def play(self, midi_file: MidiFile, loop: bool) -> None:
        self._midi_file = midi_file
        self._loop = loop

        self._block_wrote = self._synthesizer.block_size

        self._current_time = 0.0
        self._msg_index = 0

        self._block_left = create_buffer(self._synthesizer.block_size)
        self._block_right = create_buffer(self._synthesizer.block_size)

        self._synthesizer.reset()

    def stop(self) -> None:
        self._midi_file = None

        self._synthesizer.reset()

    def render(
        self,
        left: MutableSequence[float],
        right: MutableSequence[float],
        offset: Optional[int] = None,
        count: Optional[int] = None,
    ) -> None:
        if len(left) != len(right):
            raise Exception(
                "The output buffers for the left and right must be the same length."
            )

        if offset is None:
            offset = 0
        elif count is None:
            raise Exception("'count' must be set if 'offset' is set.")

        if count is None:
            count = len(left)

        wrote = 0

        while wrote < count:
            if self._block_wrote == self._synthesizer.block_size:
                self._process_events()
                self._block_wrote = 0
                self._current_time += (
                    self._synthesizer.block_size / self._synthesizer.sample_rate
                )

            src_rem = self._synthesizer.block_size - self._block_wrote
            dst_rem = count - wrote
            rem = min(src_rem, dst_rem)

            self._synthesizer.render(left, right, offset + wrote, rem)

            self._block_wrote += rem
            wrote += rem

    def _process_events(self) -> None:
        if self._midi_file is None:
            return

        while self._msg_index < len(self._midi_file._messages):  # type: ignore
            time = self._midi_file._times[self._msg_index]  # type: ignore
            msg = self._midi_file._messages[self._msg_index]  # type: ignore

            if time <= self._current_time:
                if msg.type == _MidiMessageType.NORMAL:
                    self._synthesizer.process_midi_message(
                        msg.channel, msg.command, msg.data1, msg.data2
                    )

                self._msg_index += 1

            else:
                break

        if self._msg_index == len(self._midi_file._messages) and self._loop:  # type: ignore
            self._current_time = 0.0
            self._msg_index = 0
            self._synthesizer.note_off_all(False)

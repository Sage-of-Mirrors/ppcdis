"""
Binary reader for DOL files
"""

from dataclasses import dataclass
from typing import List, Tuple

from binarybase import BinaryReader, BinarySection, SectionType

@dataclass
class DolSectionDef:
    """Container used for external code to define sections"""

    name: str
    attr: str = None
    align: int = 0x20

default_section_defs = [
    [ # Text
        DolSectionDef(".init"),
        DolSectionDef(".text")
    ],
    [ # Data
        DolSectionDef("extab_", "a"),
        DolSectionDef("extabindex_", "a"),
        DolSectionDef(".ctors"),
        DolSectionDef(".dtors"),
        DolSectionDef(".rodata"),
        DolSectionDef(".data"),
        DolSectionDef(".sdata"),
        DolSectionDef(".sdata2")
    ],
    [ # Bss
        DolSectionDef(".bss", align=0x80),
        DolSectionDef(".sbss"),
        DolSectionDef(".sbss2")
    ]
]

TEXT_COUNT = 7
DATA_COUNT = 11

OFFS_TEXT_OFFSETS = 0x0
OFFS_DATA_OFFSETS = 0x1c
OFFS_TEXT_ADDRESSES = 0x48
OFFS_DATA_ADDRESSES = 0x64
OFFS_TEXT_SIZES = 0x90
OFFS_DATA_SIZES = 0xac
OFFS_BSS_START = 0xd8
OFFS_BSS_SIZE = 0xdc
OFFS_ENTRY = 0xe0

class DolReader(BinaryReader):
    # TODO: expose changing section_defs to command line args
    def __init__(self, path: str, section_defs=default_section_defs):
        self._section_defs = section_defs
        super().__init__(path)

    def _get_sections(self) -> List[BinarySection]:
        """Finds the sections in a binary"""

        # Get section definitions
        text_defs, data_defs, bss_defs = self._section_defs

        # Get text sections
        text_offsets = self.read_word_array(OFFS_TEXT_OFFSETS, TEXT_COUNT, True)
        assert all(offs == 0 for offs in text_offsets[len(text_defs):]), \
               "Not enough text sections defined"
        text_offsets = text_offsets[:len(text_defs)]
        assert all(offs != 0 for offs in text_offsets), "Too many text sections defined"
        text_addresses = self.read_word_array(OFFS_TEXT_ADDRESSES, len(text_offsets), True)
        text_sizes = self.read_word_array(OFFS_TEXT_SIZES, len(text_offsets), True)

        # Get data sections
        data_offsets = self.read_word_array(OFFS_DATA_OFFSETS, DATA_COUNT, True)
        assert all(offs == 0 for offs in data_offsets[len(data_defs):]), \
               "Not enough data sections defined"
        data_offsets = data_offsets[:len(data_defs)]
        assert all(offs != 0 for offs in data_offsets), "Too many data sections defined"
        data_addresses = self.read_word_array(OFFS_DATA_ADDRESSES, len(data_offsets), True)
        data_sizes = self.read_word_array(OFFS_DATA_SIZES, len(data_offsets), True)
        
        # Makes section list
        sections = [
            BinarySection(sdef.name, SectionType.TEXT, offs, addr, size, sdef.attr, sdef.align)
            for sdef, offs, addr, size in zip(text_defs, text_offsets, text_addresses, text_sizes)
        ] + [
            BinarySection(sdef.name, SectionType.DATA, offs, addr, size, sdef.attr, sdef.align)
            for sdef, offs, addr, size in zip(data_defs, data_offsets, data_addresses, data_sizes)
        ]
        sections.sort(key=lambda s: s.addr)

        # Prepare bss sections
        bss_start = self.read_word(OFFS_BSS_START, True)
        bss_size = self.read_word(OFFS_BSS_SIZE, True)
        bss_end = bss_start + bss_size

        # Add unlisted bss sections
        bss_n = 0
        sections_with_bss = []
        for section in sections:
            # Section cutting bss range into sub-section
            if bss_start < section.addr <= bss_end:
                sdef = bss_defs[bss_n]
                sections_with_bss.append(
                    BinarySection(sdef.name, SectionType.BSS, 0, bss_start,
                                  section.addr - bss_start, sdef.attr,
                                  sdef.align)
                )
                bss_n += 1
                bss_start = section.addr + section.size
            # Back-to-back sections cutting bss range into 1 sub-section
            elif bss_start == section.addr:
                bss_start = section.addr + section.size
            sections_with_bss.append(section)
        if bss_start < bss_end:
            sdef = bss_defs[bss_n]
            sections_with_bss.append(
                BinarySection(sdef.name, SectionType.BSS, 0, bss_start,
                              bss_end - bss_start, sdef.attr, sdef.align)
            )

        return sections_with_bss

    def get_entries(self) -> List[Tuple[int, str]]:
        """Returns all entry functions"""
        
        return [(self.read_word(OFFS_ENTRY, True), "__start")]
    
    def get_rom_copy_info(self) -> int:
        """Gets the start address of the rom copy info in the .init section
        None if not found / irrelevant for this binary"""

        # Try get .init section
        init = self.get_section_by_name(".init")
        if init is None:
            return None

        # Try find the .init section address repeated twice
        for addr in range(init.addr, init.addr + init.size - 8, 4):
            # First copy
            if self.read_word(addr) == init.addr:
                # Second copy
                if self.read_word(addr + 4) == init.addr:
                    return addr
        
        # Not found
        return None

"""
Cell-line colours (V2.5): which cell line a run is, from its .nd2 / run file
name, and a colour family per cell line so that compare / average graphs show
every line of one cell line in shades of one colour.

Reference list: ~300 commonly used cell lines (name, aliases, colour family).
The famous ones have their own family (U2OS reds, IHH greens, HepG2 blues,
HEK293 purples, HeLa oranges, MCF7 pinks, MCF10A magentas, A549 teals,
HCT116 browns, COS-7 sky blues, CHO slate, NIH3T3 greys, Jurkat indigos ...);
the others share a family by tissue (liver = HepG2's blues, kidney = HEK's
purples, bone = U2OS's reds, cervix / uterus = HeLa's oranges, breast = MCF7's
pinks, lung = A549's teals, colon / stomach = HCT116's browns, blood = indigos,
brain / eye = cyans, skin / head and neck = golds, prostate / bladder = olives,
pancreas = limes, ovary = magentas, endothelial / muscle = maroons, fibroblasts
/ stem cells = greys, hamster / insect = slate).

Matching (match()):
  * case-insensitive; separators (-, _, space, ., /, parentheses) ignored;
  * confusable characters tolerated: O/0, I/1/l, S/5, B/8, Z/2 (both the file
    name and the aliases are folded the same way, so U20S = U2OS = u2-os);
  * the longest (most specific) alias wins (HEK293T before HEK293 before HEK;
    HeLa before HEL), ties: the earliest in the name;
  * aliases shorter than 4 characters (and names that are also words or
    people's names: STRICT_NAMES - Rat-1 / 'ratio', Dami / 'rhodamine') must stand as a token: at the start of the
    name or after a separator / a letter-digit change, and followed by the end,
    a separator or a letter-digit change (CHO in 'cho_dish2', not in 'anchor';
    EL4 in 'el4cells'); a few lab names are allowed to run on into the next word
    (IHH in 'ihhnlsmet', HEK in 'hekcells' - JOINED).
Unknown cell line -> None: the compare window asks for a colour and remembers it.
by_name(): the cell line whose name / alias IS the text (the compare window's
Cell line dropdown); names(): every known name, sorted.

Shades (shades()): an ordered list per family - mid tone first, then darker,
lighter, ... (adjacent entries differ by >= 0.12 in lightness), so the 1st, 2nd,
3rd run of one cell line are easy to tell apart.
"""
from __future__ import annotations

import colorsys
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# family: (hue in degrees, saturation)
FAMILIES: Dict[str, Tuple[float, float]] = {
    "red": (0.0, 0.78),         # U2OS, bone / sarcoma
    "orange": (27.0, 0.92),     # HeLa, cervix / uterus
    "gold": (45.0, 0.85),       # skin, melanoma, head and neck, thyroid
    "olive": (62.0, 0.60),      # prostate, bladder
    "lime": (88.0, 0.62),       # pancreas, islets
    "green": (128.0, 0.65),     # IHH, immortalised hepatocytes
    "teal": (172.0, 0.70),      # A549, lung
    "cyan": (192.0, 0.80),      # brain, nerve, eye
    "sky": (205.0, 0.75),       # COS-7, monkey cells
    "blue": (225.0, 0.78),      # HepG2, liver
    "indigo": (250.0, 0.55),    # Jurkat, blood
    "purple": (278.0, 0.60),    # HEK293, kidney
    "magenta": (305.0, 0.65),   # MCF10A, ovary
    "pink": (333.0, 0.75),      # MCF7, breast cancer
    "brown": (24.0, 0.45),      # HCT116, colon / stomach / oesophagus
    "maroon": (350.0, 0.55),    # endothelial, muscle, heart
    "grey": (0.0, 0.0),         # NIH3T3, fibroblasts, stem cells
    "slate": (212.0, 0.25),     # CHO, hamster and insect cells
}
# browns and maroons live in the dark half
_LIGHTNESS = (0.47, 0.32, 0.62, 0.39, 0.74, 0.25, 0.55, 0.82, 0.43, 0.68)
_DARK = (0.35, 0.22, 0.48, 0.29, 0.60, 0.42, 0.70, 0.18)
_GREY = (0.45, 0.25, 0.62, 0.35, 0.75, 0.15, 0.53, 0.85)

# "family: Name=alias,alias; Name=alias; ..."  (the name itself is always an alias)
_DATA = """
red: U2OS=U-2 OS,U2-OS,U2 OS; Saos-2=SAOS2; MG-63=MG63; HOS=HOS cells; 143B=143B; SJSA-1;
 MNNG/HOS=MNNG-HOS; KHOS=KHOS-240S; A-673=A673; SK-ES-1=SKES1; TC-71=TC71; RD-ES=RDES;
 MC3T3-E1=MC3T3; MLO-Y4; UMR-106=UMR106; ROS 17/2.8=ROS17; hFOB 1.19=hFOB; SK-N-MC=SKNMC;
 U-2 OS EGFP; HT-1080=HT1080; SW 872=SW872; SW 982=SW982; RH30=SJCRH30; RH4; A-204=A204
orange: HeLa=Hela S3,HeLa-S3,HeLaS3,HeLa CCL2,HeLa Kyoto; SiHa; CaSki=Ca Ski; C-33A=C33A;
 ME-180=ME180; Ishikawa; HEC-1-A=HEC1A; HEC-1-B=HEC1B; AN3CA=AN3 CA; KLE; RL95-2=RL95;
 SW756; HCC-94=HCC94; MS751; End1/E6E7; Ect1/E6E7; VK2/E6E7=VK2
gold: A375; SK-MEL-28=SKMEL28; SK-MEL-2=SKMEL2; SK-MEL-5=SKMEL5; MeWo; WM115; WM266-4=WM2664;
 WM793; WM983B; 501mel; B16-F10=B16F10,B16; B16-F1=B16F1; HaCaT; A431=A-431; SCC-13=SCC13;
 Malme-3M=MALME3M; UACC-62=UACC62; G-361=G361; COLO 829=COLO829; HT-144=HT144; NHEK;
 N/TERT-1=NTERT; Ker-CT=KerCT; FaDu; Cal27=CAL-27; SCC-25=SCC25; Detroit 562=Detroit562;
 UM-SCC-1=UMSCC1; SCC-9=SCC9; TPC-1=TPC1; BCPAP=B-CPAP; FTC-133=FTC133; 8505C;
 Nthy-ori 3-1=Nthyori; YUMM1.7=YUMM; 1205Lu
olive: PC-3=PC3; DU145=DU-145; LNCaP=LNCAP clone FGC; 22Rv1=22RV1; VCaP; C4-2=C42; C4-2B=C42B;
 RWPE-1=RWPE1; PNT1A=PNT1-A; LAPC4=LAPC-4; Myc-CaP=MycCaP; TRAMP-C1=TRAMPC1; T24; RT4;
 HTB-9=5637 bladder,5637-HTB9; UM-UC-3=UMUC3; J82; HT-1376=HT1376; RT112=RT-112; SV-HUC-1=SVHUC1; MB49
lime: PANC-1=PANC1; MIA PaCa-2=MIAPaCa2,MiaPaCa; BxPC-3=BXPC3; AsPC-1=ASPC1; Capan-1=CAPAN1;
 Capan-2=CAPAN2; CFPAC-1=CFPAC1; HPAF-II=HPAFII; PaTu 8988T=PATU8988T; SU.86.86=SU8686;
 Panc 02=PANC02; KPC; INS-1=INS1; INS-1E=INS1E,INS-1 832/13,INS832/13; MIN6=MIN-6;
 betaTC-6=BTC6,betaTC6; alphaTC1-6=alphaTC1; RIN-m5F=RINm5F; HPDE; hTERT-HPNE=HPNE; EndoC-betaH1=EndoC
green: IHH=IHH cells; THLE-2=THLE2; THLE-3=THLE3; PH5CH8; HHL-5=HHL5; Fa2N-4=Fa2N4; HepLi
teal: A549=A-549; NCI-H1299=H1299; NCI-H460=H460; NCI-H1975=H1975; HCC827; PC-9=PC9;
 Calu-3=CALU3; Calu-6=CALU6; NCI-H358=H358; NCI-H441=H441; NCI-H23=H23; NCI-H522=H522;
 NCI-H1650=H1650; NCI-H2009=H2009; NCI-H3122=H3122; BEAS-2B=BEAS2B; 16HBE14o-=16HBE;
 LLC=Lewis lung,LLC1; MLE-12=MLE12; NCI-H69=H69; NCI-H82=H82; NCI-H146=H146; NCI-H520=H520;
 SK-MES-1=SKMES1; HCC4006; EKVX; NCI-H1703=H1703; NCI-H226=H226; A427; Calu-1=CALU1;
 HBEC3-KT=HBEC3KT; NuLi-1=NuLi1; MLE-15=MLE15; Small airway epithelial=SAEC
cyan: SH-SY5Y=SHSY5Y,SHSY-5Y; SK-N-SH=SKNSH; SK-N-BE(2)=SKNBE2,SK-N-BE; IMR-32=IMR32; Kelly;
 LAN-5=LAN5; BE(2)-C=BE2C; PC12=PC-12; Neuro-2a=Neuro2a,N2a,N2A cells; NG108-15=NG108;
 U-87 MG=U87MG,U87,U-87; U-251 MG=U251,U251MG; U-118 MG=U118; T98G; LN-229=LN229; LN-18=LN18;
 A172; SF-295=SF295; SNB-19=SNB19; GL261; C6 glioma=C6-glioma; HT22=HT-22; NSC-34=NSC34;
 ReNcell VM=ReNcell; LUHMES; CAD cells=CATH.a differentiated; SK-N-AS=SKNAS; SK-N-DZ=SKNDZ;
 Daoy; D283 Med=D283; hCMEC/D3=hCMEC,HCMECD3; N9 microglia=N9; BV-2=BV2; HMC3; SVGp12=SVG p12;
 hTERT RPE-1=RPE-1,RPE1,hTERTRPE1; ARPE-19=ARPE19; 661W; WERI-Rb-1=WERIRb1; Y79; Muller MIO-M1=MIOM1
sky: COS-7=COS7; COS-1=COS1; CV-1=CV1; Vero=Vero E6,VeroE6,Vero CCL81; MA-104=MA104; LLC-MK2=LLCMK2;
 BSC-1=BSC1,BS-C-1; FRhK-4=FRhK4; MARC-145=MARC145
blue: HepG2=Hep G2,Hep-G2,HEPG2 C3A; Hep3B=Hep 3B,Hep-3B; Huh7=Huh-7,HUH 7; Huh-7.5=Huh7.5,Huh75;
 PLC/PRF/5=PLCPRF5; SK-HEP-1=SKHEP1; SNU-449=SNU449; SNU-387=SNU387; SNU-423=SNU423;
 SNU-475=SNU475; HLE; HLF; HepaRG=Hepa RG; Hepa1-6=Hepa 1-6,Hepa16; Hepa 1c1c7=Hepa1c1c7;
 AML12=AML-12; BNL CL.2=BNLCL2; H4IIE=H4-II-E; FaO=Fao cells; McA-RH7777=McARH7777,McA;
 C3A; Li-7=Li7; JHH-7=JHH7; Huh-1=Huh1; HuH-6=Huh6; HepG2.2.15=HepG22.15; MHCC97H=MHCC97;
 SMMC-7721=SMMC7721; Bel-7402=BEL7402; LO2=L-02,L02; QSG-7701=QSG7701; HepaG2
indigo: Jurkat=Jurkat E6-1,JurkatE61; K562=K-562; HL-60=HL60; THP-1=THP1; U-937=U937;
 Raji; Daudi; Ramos; MOLT-4=MOLT4; CCRF-CEM=CCRFCEM,CEM; KG-1=KG1; Kasumi-1=Kasumi1;
 MV4-11=MV411; MOLM-13=MOLM13; OCI-AML3=OCIAML3; NB4; HEL 92.1.7=HEL; RPMI 8226=RPMI8226;
 U266=U-266; MM.1S=MM1S,MM1.S; KMS-11=KMS11; OPM-2=OPM2; Namalwa; SU-DHL-4=SUDHL4;
 SU-DHL-6=SUDHL6; OCI-Ly3=OCILY3; OCI-Ly10=OCILY10; Karpas 299=Karpas299; HuT 78=HUT78;
 KG-1a=KG1a; Ba/F3=BaF3; RAW 264.7=RAW264.7,RAW264,RAW; J774A.1=J774,J774A1; P388D1;
 EL4=EL-4; A20; WEHI-3=WEHI3; 32D=32Dcl3; HPC-7=HPC7; MEL cells=MEL; DT40; NK-92=NK92;
 YT cells=YTS; Kit225; Hut-102=HUT102; Mono Mac 6=MonoMac6; MEG-01=MEG01; Dami; EoL-1=EOL1;
 SUP-T1=SUPT1; Loucy; RS4-11=RS411,RS4 11; REH; NALM-6=NALM6; SEM cells; L-1236=L1236; KM-H2=KMH2
purple: HEK293=HEK 293,HEK-293,HEK,293 cells,293; HEK293T=HEK 293T,293T,293-T; 293FT=HEK293FT;
 293A=HEK293A; Expi293=Expi293F; FreeStyle 293=FreeStyle293,293F; Lenti-X 293T=LentiX;
 HEK293S=293S; Flp-In T-REx 293=FlpIn293,TREx293; MDCK=MDCK II,MDCKII; LLC-PK1=LLCPK1;
 HK-2=HK2; NRK-52E=NRK52E; NRK; IMCD3=mIMCD-3,mIMCD3; 786-O=786O; ACHN; Caki-1=CAKI1;
 Caki-2=CAKI2; A-498=A498; RPTEC/TERT1=RPTEC; PtK2=PTK-2; PtK1; HK-2 cells; mpkCCD=mpkCCDc14;
 M-1 cortical collecting duct=M1CCD; RCC4; 769-P=769P; HEK-Blue=HEKBlue
magenta: MCF10A=MCF-10A,MCF 10A,MCF10-A; MCF10AT=MCF-10AT; MCF10CA1a=MCF10CA1A; MCF-12A=MCF12A;
 184A1; HMEC=hTERT-HME1,HME1; SKOV3=SK-OV-3; OVCAR-3=OVCAR3,NIH:OVCAR-3; OVCAR-4=OVCAR4;
 OVCAR-5=OVCAR5; OVCAR-8=OVCAR8; A2780; CAOV-3=CAOV3; ES-2=ES2; OV-90=OV90; ID8; Kuramochi;
 COV362; PEO1; PEO4; IGROV-1=IGROV1; HEY=HEY-A8,HeyA8; OVSAHO; OVCAR-433=OVCAR433
pink: MCF7=MCF-7,MCF 7,MCF7 cells; T47D=T-47D,T47-D; MDA-MB-231=MDAMB231,MDA231,MB231;
 MDA-MB-468=MDAMB468,MDA468; MDA-MB-453=MDAMB453; MDA-MB-361=MDAMB361; MDA-MB-436=MDAMB436;
 SK-BR-3=SKBR3; BT-474=BT474; BT-549=BT549; BT-20=BT20; ZR-75-1=ZR751; HCC1937; HCC1806;
 HCC38; HCC70; HCC1954; Hs 578T=Hs578T; CAL-51=CAL51; SUM149PT=SUM149; SUM159PT=SUM159;
 4T1; EMT6; E0771=EO771; MDA-MB-157=MDAMB157; MDA-MB-415=MDAMB415; CAMA-1=CAMA1; EFM-19=EFM19;
 HCC1428; UACC-812=UACC812; JIMT-1=JIMT1; MCF7-TamR=MCF7TamR
brown: HCT116=HCT 116,HCT-116; HT-29=HT29; Caco-2=CACO2,Caco2 BBe,C2BBe1; SW480=SW-480;
 SW620=SW-620; DLD-1=DLD1; LoVo; LS174T=LS 174T,LS-174T; LS180=LS 180; RKO; COLO 205=COLO205;
 COLO 320=COLO320; HCT-15=HCT15; T84; LIM1215; SW48; SW1116; HT-115=HT115; CT26=CT-26;
 MC38=MC-38; IEC-6=IEC6; IEC-18=IEC18; AGS; MKN45=MKN-45; NCI-N87=N87; KATO III=KATOIII;
 SNU-1=SNU1; OE33; OE19; KYSE-30=KYSE30; KYSE-150=KYSE150; TE-1=TE1; FLO-1=FLO1;
 HT-29 MTX=HT29MTX; LS513; SW837; NCM460; CCD 841 CoN=CCD841; Het-1A=Het1A; GES-1=GES1;
 MKN28; SGC-7901=SGC7901; HGC-27=HGC27; YAMC; MODE-K=MODEK
maroon: HUVEC=HUVECs; HMEC-1=HMEC1; EA.hy926=EAhy926,EA.hy 926; HAEC; HCAEC; HDMEC; TIME-HMVEC=hTERT-TIME;
 bEnd.3=bEnd3; MS1=MILE SVEN 1; SVEC4-10=SVEC410; HPAEC; HAoSMC; A7r5=A7R5; A10 cells;
 C2C12=C2-C12; H9c2=H9C2; L6 myoblasts=L6; AC16; HL-1=HL1 cardiomyocytes; HSkMC; LHCN-M2=LHCNM2;
 iPSC-CM=iPSCCM,hiPSC-CM; MOVAS; HCASMC; HUVSMC; HMVEC; HDLEC; 3B-11=3B11
grey: NIH3T3=NIH 3T3,NIH-3T3,3T3; 3T3-L1=3T3L1; MEF=MEFs; IMR-90=IMR90; WI-38=WI38; MRC-5=MRC5;
 BJ=BJ-5ta,BJ fibroblasts,BJ5ta; HFF-1=HFF1,HFF; Hs27; L929=L-929,L cells; Swiss 3T3=Swiss3T3;
 Balb/3T3=Balb3T3; Rat-1=Rat1; Rat-2=Rat2; REF52; 10T1/2=C3H10T1/2,10T12; NRK-49F=NRK49F;
 TIG-3=TIG3; CCD-18Co=CCD18Co; NHDF=HDF; 3T3-J2=3T3J2; Hs68; 3T3-F442A=3T3F442A; OP9; ST2 stromal=ST2;
 H1-hESC=H1 hESC,WA01; H9-hESC=H9 hESC,WA09; HUES9=HUES-9; WTC-11=WTC11; KOLF2.1J=KOLF2;
 PGP1; E14Tg2a=E14TG2A,E14 mESC; mESC; NTERA-2=NT2,NTERA2; P19; F9 cells=F9; iPSC=hiPSC,iPSCs;
 HS-5=HS5; HS-27A=HS27A; LX-2=LX2; HSC-T6=HSCT6
slate: CHO=CHO cells; CHO-K1=CHOK1; CHO-DG44=CHODG44; CHO-S=CHOS; ExpiCHO=ExpiCHO-S; BHK-21=BHK21,BHK;
 Sf9=SF-9,Sf 9; Sf21=SF-21; High Five=Hi5,HighFive,BTI-TN-5B1-4; Drosophila S2=S2R+,Schneider 2,SchneiderS2;
 Kc167=KC167; V79; CHO-AA8=AA8; DF-1=DF1; QT6; DT40 chicken; LMH; Xenopus A6=XTC; ZF4; PAC2; BmN
"""

# lab names that may run on into the next word ('ihhnlsmet', 'hekcells')
JOINED = {"ihh", "hek"}
# names that are also words / people's names / parts of words: always need token
# boundaries, whatever their length (Rat-1 in 'ratio', Dami in 'rhodamine' ...)
STRICT_NAMES = ("Rat-1", "Rat-2", "Dami", "Kelly", "Ramos", "Raji", "Daudi", "Loucy",
                "Namalwa", "Ishikawa", "Kuramochi", "HeyA8", "HEY", "REH", "Daoy")
_FOLD = str.maketrans({"0": "o", "1": "i", "l": "i", "5": "s", "8": "b", "2": "z"})


@dataclass
class CellLine:
    name: str
    family: str
    aliases: List[str] = field(default_factory=list)


def fold(text: str) -> str:
    """Lower case, separators dropped, confusables folded (O/0, I/1/l, S/5, B/8, Z/2)."""
    return re.sub(r"[^0-9a-z]", "", str(text).lower()).translate(_FOLD)


def _parse() -> List[CellLine]:
    out: List[CellLine] = []
    fam = None
    blob = re.sub(r"\n\s+", " ", _DATA.strip())
    for line in blob.splitlines():
        line = line.strip()
        if not line:
            continue
        fam, rest = line.split(":", 1)
        fam = fam.strip()
        if fam not in FAMILIES:
            raise ValueError(f"unknown family {fam}")
        for ent in rest.split(";"):
            ent = ent.strip()
            if not ent:
                continue
            name, _eq, al = ent.partition("=")
            names = [name.strip()] + [a.strip() for a in al.split(",") if a.strip()]
            out.append(CellLine(name=name.strip(), family=fam, aliases=names))
    return out


CELL_LINES: List[CellLine] = _parse()
_INDEX: List[Tuple[str, CellLine]] = sorted(
    {(fold(a), id(c)): (fold(a), c) for c in CELL_LINES for a in c.aliases if fold(a)}.values(),
    key=lambda t: -len(t[0]))


_STRICT = {fold(a) for c in CELL_LINES if c.name in STRICT_NAMES for a in c.aliases}


def _kind(ch: str) -> str:
    return "d" if ch.isdigit() else ("a" if ch.isalpha() else "s")


def _folded_map(text: str) -> Tuple[str, List[int], str]:
    """(folded text, index in `low` of each folded char, low = text lower-cased)."""
    low = str(text).lower()
    chars, pos = [], []
    for i, ch in enumerate(low):
        if ch.isascii() and ch.isalnum():
            chars.append(ch.translate(_FOLD))
            pos.append(i)
    return "".join(chars), pos, low


def _token_ok(low: str, start: int, end: int, alias_f: str, joined: bool) -> bool:
    """start / end: indices in `low` of the first / last char of the match."""
    first, last = low[start], low[end]
    left_ok = start == 0 or _kind(low[start - 1]) == "s" or \
        _kind(low[start - 1]) != _kind(first)
    if not left_ok:
        return False
    if end + 1 >= len(low):
        return True
    nxt = low[end + 1]
    if _kind(nxt) == "s" or _kind(nxt) != _kind(last):
        return True
    return joined


def match(text: str) -> Optional[CellLine]:
    """The cell line named in a file / run / group name, or None."""
    if not text:
        return None
    from pathlib import Path
    stem = Path(str(text)).name
    stem = re.sub(r"\.(nd2|npz|prism|csv|xlsx)$", "", stem, flags=re.I)
    f, pos, low = _folded_map(stem)
    best = None
    for alias_f, cl in _INDEX:
        if best is not None and len(alias_f) < len(best[0]):
            break
        i = f.find(alias_f)
        while i >= 0:
            s, e = pos[i], pos[i + len(alias_f) - 1]
            if (len(alias_f) >= 4 and alias_f not in _STRICT) or                     _token_ok(low, s, e, alias_f, alias_f in JOINED):
                if best is None or len(alias_f) > len(best[0]) or \
                        (len(alias_f) == len(best[0]) and i < best[1]):
                    best = (alias_f, i, cl)
                break
            i = f.find(alias_f, i + 1)
    return best[2] if best else None


def shades(family: str, n: int) -> List[str]:
    """n distinguishable shades of a family, in a fixed order (mid, dark, light ...);
    more than the base list: the list repeats with a small hue shift."""
    h, s = FAMILIES.get(family, (0.0, 0.0))
    ls = _GREY if s == 0 else (_DARK if family in ("brown", "maroon") else _LIGHTNESS)
    out = []
    for k in range(max(0, n)):
        r = k // len(ls)
        hh = ((h + 9.0 * r * (1 if r % 2 else -1)) % 360.0) / 360.0
        rgb = colorsys.hls_to_rgb(hh, ls[k % len(ls)], s)
        out.append("#" + "".join(f"{int(round(c * 255)):02X}" for c in rgb))
    return out


_BY_NAME: Dict[str, CellLine] = {}
for _c in CELL_LINES:                               # the names first, then the aliases
    _BY_NAME.setdefault(fold(_c.name), _c)
for _c in CELL_LINES:
    for _a in _c.aliases:
        if fold(_a):
            _BY_NAME.setdefault(fold(_a), _c)


def by_name(text: str) -> Optional[CellLine]:
    """The cell line whose name or alias IS this text (separators, case and
    confusable characters ignored, as in match()) - not a search inside a longer
    name. None = not a known cell line (e.g. a name the user typed)."""
    return _BY_NAME.get(fold(text)) if text and fold(text) else None


def names() -> List[str]:
    """Every known cell line's name, sorted (case-insensitive)."""
    return sorted({c.name for c in CELL_LINES}, key=lambda s: (s.lower(), s))


def shades_of(colour: str, n: int) -> List[str]:
    """n shades around one colour (a cell line the user named and gave a colour):
    the colour itself first, then darker / lighter steps of its hue."""
    try:
        rgb = tuple(int(colour.lstrip("#")[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return [colour] * max(0, n)
    h, l0, s = colorsys.rgb_to_hls(*rgb)
    steps = (0.0, -0.15, 0.15, -0.27, 0.27, -0.08, 0.08, -0.21, 0.21, 0.35)
    out = ["#" + "".join(f"{int(round(c * 255)):02X}" for c in rgb)] if n > 0 else []
    for k in range(1, max(0, n)):
        ll = min(0.88, max(0.12, l0 + steps[k % len(steps)]))
        c = colorsys.hls_to_rgb((h + 0.02 * (k // len(steps))) % 1.0, ll, s)
        out.append("#" + "".join(f"{int(round(v * 255)):02X}" for v in c))
    return out


def assign_colours(names: Sequence[str], remembered: Optional[Dict[str, str]] = None,
                   lines: Optional[Sequence] = None) -> List[Optional[str]]:
    """One colour per name (run / group): a remembered colour (key = name lower
    case) wins; otherwise the k-th name of a cell line gets the k-th shade of its
    family. None = unknown cell line and no remembered colour (ask the user).

    lines (V2.5, optional, one per name): the cell line chosen by the user -
    a CellLine (its family), a str = a cell line the user named that is not in
    the list (shades of the colour remembered for that name; None while it has
    none), '' = 'Unknown' on purpose (no family), None = read it from the name."""
    remembered = {str(k).lower(): v for k, v in (remembered or {}).items()}
    lines = list(lines) if lines is not None else [None] * len(names)
    fams: List[Optional[str]] = []
    for nm, ln in zip(names, lines + [None] * (len(names) - len(lines))):
        if isinstance(ln, CellLine):
            fams.append(ln.family)
        elif isinstance(ln, str):
            fams.append("custom:" + ln.strip().lower() if ln.strip() else None)
        else:
            cl = match(nm)
            fams.append(cl.family if cl is not None else None)
    need: Dict[str, int] = {}
    for f in fams:
        if f is not None:
            need[f] = need.get(f, 0) + 1
    pal: Dict[str, Optional[List[str]]] = {}
    for f, k in need.items():
        if f.startswith("custom:"):
            base = remembered.get(f[7:])
            pal[f] = shades_of(base, k) if base else None
        else:
            pal[f] = shades(f, k)
    count: Dict[str, int] = {}
    out: List[Optional[str]] = []
    for nm, f in zip(names, fams):
        key = str(nm).lower()
        if key in remembered:
            out.append(remembered[key])
            if f is not None:
                count[f] = count.get(f, 0) + 1
            continue
        if f is None or pal.get(f) is None:
            out.append(None)
            continue
        k = count.get(f, 0)
        count[f] = k + 1
        out.append(pal[f][k])
    return out

import dace
import numpy as np


NBLOCKS = dace.symbol('NBLOCKS')
# KLEV = dace.symbol('KLEV')
KLEV = 137
NCLV = dace.symbol('NCLV')
KLON = dace.symbol('KLON')
NCLDTOP = dace.symbol('NCLDTOP')
KFDIA = dace.symbol('KFDIA')
KIDIA = dace.symbol('KIDIA')
NCLDQL = dace.symbol('NCLDQL')
NCLDQI = dace.symbol('NCLDQI')
NCLDQS = dace.symbol('NCLDQS')


@dace.program
def inner_loops_7(
        PTSPHY: dace.float64,
        RLMIN: dace.float64,
        ZEPSEC: dace.float64,
        RG: dace.float64,
        RTHOMO: dace.float64,
        ZALFAW: dace.float64,
        PLU_NF: dace.float64[KLON, KLEV],
        LDCUM_NF: dace.int32[KLON],
        PSNDE_NF: dace.float64[KLON, KLEV],
        PAPH_NF: dace.float64[KLON, KLEV+1],
        PSUPSAT_NF: dace.float64[KLON, KLEV],
        PT_NF: dace.float64[KLON, KLEV],
        tendency_tmp_t_NF: dace.float64[KLON, KLEV],
        PLUDE_NF: dace.float64[KLON, KLEV]
        ):

    ZCONVSRCE = np.zeros([KLON, NCLV], dtype=np.float64)
    ZSOLQA = np.zeros([KLON, NCLV, NCLV], dtype=np.float64)
    ZDTGDP = np.zeros([KLON], dtype=np.float64)
    ZDP = np.zeros([KLON], dtype=np.float64)
    ZGDP = np.zeros([KLON], dtype=np.float64)
    ZTP1 = np.zeros([KLON], dtype=np.float64)

    for JK in range(NCLDTOP, KLEV-1):
        for JL in range(KIDIA, KFDIA):
            ZTP1[JL] = PT_NF[JL, JK] + PTSPHY * tendency_tmp_t_NF[JL, JK]
            if PSUPSAT_NF[JL, JK] > ZEPSEC:
                if ZTP1[JL] > RTHOMO:
                    ZSOLQA[JL, NCLDQL, NCLDQL] = ZSOLQA[JL, NCLDQL, NCLDQL] + PSUPSAT_NF[JL, JK]
                else:
                    ZSOLQA[JL, NCLDQI, NCLDQI] = ZSOLQA[JL, NCLDQI, NCLDQI] + PSUPSAT_NF[JL, JK]

        for JL in range(KIDIA, KFDIA):
            ZDP[JL] = PAPH_NF[JL, JK+1]-PAPH_NF[JL, JK]
            ZGDP[JL] = RG/ZDP[JL]
            ZDTGDP[JL] = PTSPHY*ZGDP[JL]

        for JL in range(KIDIA, KFDIA):
            PLUDE_NF[JL, JK] = PLUDE_NF[JL, JK]*ZDTGDP[JL]
            if LDCUM_NF[JL] and PLUDE_NF[JL, JK] > RLMIN and PLU_NF[JL, JK+1] > ZEPSEC:
                ZCONVSRCE[JL, NCLDQL] = ZALFAW*PLUDE_NF[JL, JK]
                ZCONVSRCE[JL, NCLDQI] = [1.0 - ZALFAW]*PLUDE_NF[JL, JK]
                ZSOLQA[JL, NCLDQL, NCLDQL] = ZSOLQA[JL, NCLDQL, NCLDQL]+ZCONVSRCE[JL, NCLDQL]
                ZSOLQA[JL, NCLDQI, NCLDQI] = ZSOLQA[JL, NCLDQI, NCLDQI]+ZCONVSRCE[JL, NCLDQI]
            else:
                PLUDE_NF[JL, JK] = 0.0

            if LDCUM_NF[JL]:
                ZSOLQA[JL, NCLDQS, NCLDQS] = ZSOLQA[JL, NCLDQS, NCLDQS] + PSNDE_NF[JL, JK]*ZDTGDP[JL]


@dace.program
def vert_loop_7(
            PTSPHY: dace.float64,
            RLMIN: dace.float64,
            ZEPSEC: dace.float64,
            RG: dace.float64,
            RTHOMO: dace.float64,
            ZALFAW: dace.float64,
            PLU_NF: dace.float64[KLON, KLEV, NBLOCKS],
            LDCUM_NF: dace.int32[KLON, NBLOCKS],
            PSNDE_NF: dace.float64[KLON, KLEV, NBLOCKS],
            PAPH_NF: dace.float64[KLON, KLEV+1, NBLOCKS],
            PSUPSAT_NF: dace.float64[KLON, KLEV, NBLOCKS],
            PT_NF: dace.float64[KLON, KLEV, NBLOCKS],
            tendency_tmp_t_NF: dace.float64[KLON, KLEV, NBLOCKS],
            PLUDE_NF: dace.float64[KLON, KLEV, NBLOCKS]
        ):

    for JN in dace.map[0:NBLOCKS:KLON]:
        inner_loops_7(
            PTSPHY,  RLMIN,  ZEPSEC,  RG,  RTHOMO,  ZALFAW,  PLU_NF[:, :, JN],  LDCUM_NF[:, JN],  PSNDE_NF[:, :, JN],
            PAPH_NF[:, :, JN], PSUPSAT_NF[:, :, JN],  PT_NF[:, :, JN],  tendency_tmp_t_NF[:, :, JN], PLUDE_NF[:, :, JN],
            NCLV=NCLV, NCLDTOP=NCLDTOP, KIDIA=KIDIA, KFDIA=KFDIA, NCLDQL=NCLDQL, NCLDQI=NCLDQI,
            NCLDQS=NCLDQS)

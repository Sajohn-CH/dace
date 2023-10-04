PROGRAM mwe_map_similar_size_5
    INTEGER, PARAMETER :: JPIM = SELECTED_INT_KIND(9)
    INTEGER, PARAMETER :: JPRB = SELECTED_REAL_KIND(13, 300)

    INTEGER(KIND=JPIM), PARAMETER  :: KLEV = 137
    INTEGER(KIND=JPIM), PARAMETER  :: NCLV = 10
    INTEGER(KIND=JPIM), PARAMETER  :: NBLOCKS = 200
    INTEGER(KIND=JPIM), PARAMETER :: NCLDQI = 3
    INTEGER(KIND=JPIM), PARAMETER :: NCLDQL = 4

    REAL(KIND=JPRB) INP1(NBLOCKS, KLEV)
    REAL(KIND=JPRB) INP2(NBLOCKS, KLEV, NCLV)
    REAL(KIND=JPRB) OUT1(NBLOCKS, KLEV)

    CALL mwe_map_similar_size_5_routine(&
        & KLEV, NBLOCKS, NCLV, NCLDQI, NCLDQL, &
        & INP1, INP2, OUT1)

END PROGRAM

SUBROUTINE mwe_map_similar_size_5_routine(&
        & KLEV, NBLOCKS, NCLV, NCLDQI, NCLDQL, &
        & INP1, INP2, OUT1)

    INTEGER, PARAMETER :: JPIM = SELECTED_INT_KIND(9)
    INTEGER, PARAMETER :: JPRB = SELECTED_REAL_KIND(13, 300)

    INTEGER(KIND=JPIM) KLEV
    INTEGER(KIND=JPIM) NBLOCKS
    INTEGER(KIND=JPIM) NCLV
    INTEGER(KIND=JPIM) NCLDQI
    INTEGER(KIND=JPIM) NCLDQL

    REAL(KIND=JPRB) INP1(NBLOCKS, KLEV)
    REAL(KIND=JPRB) INP2(NBLOCKS, KLEV, NCLV)
    REAL(KIND=JPRB) OUT1(NBLOCKS, KLEV)
        
    INTEGER JN = 1
    CALL inner_loops(KLEV, NCLV, NCLDQI, NCLDQL, INP1(JN, :), INP2(JN, :, :), OUT1(JN, :))

END SUBROUTINE mwe_map_similar_size_5_routine

SUBROUTINE inner_loops(&
        & KLEV, NCLV, NCLDQI, NCLDQL, &
        & INP1, INP2, OUT1)
    INTEGER, PARAMETER :: JPIM = SELECTED_INT_KIND(9)
    INTEGER, PARAMETER :: JPRB = SELECTED_REAL_KIND(13, 300)

    INTEGER(KIND=JPIM) KLEV
    INTEGER(KIND=JPIM) NCLV
    INTEGER(KIND=JPIM) NCLDQI
    INTEGER(KIND=JPIM) NCLDQL

    REAL(KIND=JPRB) INP1(KLEV)
    REAL(KIND=JPRB) INP2(KLEV, NCLV)
    REAL(KIND=JPRB) OUT1(KLEV)

    DO JK=1,KLEV
        OUT1(JK) = INP2(JK, NCLDQL)
    ENDDO

    DO JK=5,KLEV
        OUT1(JK) = OUT1(JK-1) + INP1(JK)
    ENDDO

END SUBROUTINE inner_loops

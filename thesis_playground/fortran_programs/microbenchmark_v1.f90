PROGRAM map_loop_1
    INTEGER, PARAMETER :: JPIM = SELECTED_INT_KIND(9)
    INTEGER, PARAMETER :: JPRB = SELECTED_REAL_KIND(13, 300)

    INTEGER(KIND=JPIM), PARAMETER  :: KLEV = 100
    INTEGER(KIND=JPIM), PARAMETER  :: NBLOCKS = 100

    REAL(KIND=JPRB) INPUT(KLEV, NBLOCKS)
    REAL(KIND=JPRB) OUTPUT(KLEV, NBLOCKS)

    CALL map_loop_1_routine(KLEV, NBLOCKS, INPUT, OUTPUT)
    
END PROGRAM

SUBROUTINE map_loop_1_routine(KLEV, NBLOCKS, INPUT, OUTPUT)
    INTEGER, PARAMETER :: JPIM = SELECTED_INT_KIND(9)
    INTEGER, PARAMETER :: JPRB = SELECTED_REAL_KIND(13, 300)

    INTEGER(KIND=JPIM) KLEV
    INTEGER(KIND=JPIM) NBLOCKS

    REAL(KIND=JPRB) INPUT(KLEV, NBLOCKS)
    REAL(KIND=JPRB) OUTPUT(KLEV, NBLOCKS)
    REAL(KIND=JPRB) TMP(KLEV, NBLOCKS)


    DO I=1,NBLOCKS
        DO J=3,KLEV
            TMP(J,I) = (INPUT(J,I) + INPUT(J-1, I) + INPUT(J-2, I)) * 3
            OUTPUT(J,I) = (TMP(J,I) + TMP(J-1, I) + TMP(J-2, I)) * 3
        ENDDO
    ENDDO

END SUBROUTINE map_loop_1_routine

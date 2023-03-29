PROGRAM cloud_evaporation_within_layer

    INTEGER, PARAMETER :: JPIM = SELECTED_INT_KIND(9)
    INTEGER, PARAMETER :: JPRB = SELECTED_REAL_KIND(13, 300)

    INTEGER(KIND=JPIM), PARAMETER  :: KLON = 100
    INTEGER(KIND=JPIM), PARAMETER  :: KLEV = 100
    INTEGER(KIND=JPIM), PARAMETER  :: NCLV = 100
    INTEGER(KIND=JPIM)  :: KIDIA 
    INTEGER(KIND=JPIM)  :: KFDIA

    ! INPUT
    REAL(KIND=JPRB)     :: PMFU(KLON,KLEV)
    REAL(KIND=JPRB)     :: PMFD(KLON,KLEV)
    REAL(KIND=JPRB)     :: ZDTGDP(KLON)
    REAL(KIND=JPRB)     :: ZANEWM1(KLON)
    LOGICAL             :: LLFALL(NCLV)
    INTEGER(KIND=JPIM)  :: IPHASE(NCLV) 
    REAL(KIND=JPRB)     :: ZQXNM1(KLON,NCLV)

    ! INPUT/OUTPUT
    REAL(KIND=JPRB)     :: ZACUST(KLON)
    REAL(KIND=JPRB)     :: ZCONVSRCE(KLON,NCLV)


    CALL cloud_evaporation_within_layer_routine(&
    & KLON, KLEV, KIDIA, KFDIA, NCLV, &
    & PMFU, PMFD, ZDTGDP, ZANEWM1, LLFALL, IPHASE, ZQXNM1, &
    & ZACUST, ZCONVSRCE)

END

SUBROUTINE cloud_evaporation_within_layer_routine(&
        & KLON, KLEV, KIDIA, KFDIA, NCLV, &
        & PMFU, PMFD, ZDTGDP, ZANEWM1, LLFALL, IPHASE, ZQXNM1, &
        & ZACUST, ZCONVSRCE)

    INTEGER, PARAMETER :: JPIM = SELECTED_INT_KIND(9)
    INTEGER, PARAMETER :: JPRB = SELECTED_REAL_KIND(13, 300)

    ! PARAMETERS
    INTEGER(KIND=JPIM)  :: KLON
    INTEGER(KIND=JPIM)  :: KLEV
    INTEGER(KIND=JPIM)  :: KIDIA 
    INTEGER(KIND=JPIM)  :: KFDIA 
    INTEGER(KIND=JPIM)  :: NCLV

    ! INPUT
    REAL(KIND=JPRB)     :: PMFU(KLON,KLEV)
    REAL(KIND=JPRB)     :: PMFD(KLON,KLEV)
    REAL(KIND=JPRB)     :: ZDTGDP(KLON)
    REAL(KIND=JPRB)     :: ZANEWM1(KLON)
    LOGICAL             :: LLFALL(NCLV)
    INTEGER(KIND=JPIM)  :: IPHASE(NCLV) 
    REAL(KIND=JPRB)     :: ZQXNM1(KLON,NCLV)

    ! INPUT/OUTPUT
    REAL(KIND=JPRB)     :: ZACUST(KLON)
    REAL(KIND=JPRB)     :: ZCONVSRCE(KLON,NCLV)

    ! LOCALS
    INTEGER(KIND=JPIM)  :: JK
    REAL(KIND=JPRB)     :: ZLCUST(KLON,NCLV)
    REAL(KIND=JPRB)     :: ZMF(KLON)

    JK = 1

    DO JL=KIDIA,KFDIA
        ZMF(JL)=MAX(0.0,(PMFU(JL,JK)+PMFD(JL,JK))*ZDTGDP(JL))
        ZACUST(JL)=ZMF(JL)*ZANEWM1(JL)
    ENDDO
  
    DO JM=1,NCLV
        IF (.NOT.LLFALL(JM).AND.IPHASE(JM)>0) THEN 
            DO JL=KIDIA,KFDIA
                ZLCUST(JL,JM)=ZMF(JL)*ZQXNM1(JL,JM)
                ! record total flux for enthalpy budget:
                ZCONVSRCE(JL,JM)=ZCONVSRCE(JL,JM)+ZLCUST(JL,JM)
            ENDDO
        ENDIF
    ENDDO

END SUBROUTINE cloud_evaporation_within_layer_routine


!Flipped arrrays and caching
PROGRAM vert_loop_7_no_klon


    INTEGER, PARAMETER :: JPIM = SELECTED_INT_KIND(9)
    INTEGER, PARAMETER :: JPRB = SELECTED_REAL_KIND(13, 300)

    INTEGER(KIND=JPIM), PARAMETER  :: KLEV = 100
    INTEGER(KIND=JPIM), PARAMETER  :: NCLV = 100
    INTEGER(KIND=JPIM), PARAMETER  :: NBLOCKS = 100

    ! Parameters
    INTEGER(KIND=JPIM) KIDIA 
    INTEGER(KIND=JPIM) KFDIA 
    INTEGER(KIND=JPIM) NCLDQS 
    INTEGER(KIND=JPIM) NCLDQI 
    INTEGER(KIND=JPIM) NCLDQL 
    INTEGER(KIND=JPIM) NCLDTOP

    ! input
    REAL(KIND=JPRB) PTSPHY
    REAL(KIND=JPRB) RLMIN
    REAL(KIND=JPRB) ZEPSEC
    REAL(KIND=JPRB) RG
    ! was a temporary scalar before, to complicated to include whole computation here
    REAL(KIND=JPRB) ZALFAW
    REAL(KIND=JPRB) RTHOMO
    REAL(KIND=JPRB) PLU(NBLOCKS, KLEV)
    INTEGER(KIND=JPIM) LDCUM(NBLOCKS)
    REAL(KIND=JPRB) PSNDE(NBLOCKS, KLEV)
    REAL(KIND=JPRB) PAPH(NBLOCKS, KLEV+1)
    ! This could be different in memory
    REAL(KIND=JPRB) PSUPSAT(NBLOCKS, KLEV)
    REAL(KIND=JPRB) PT(NBLOCKS, KLEV)
    REAL(KIND=JPRB) tendency_tmp_T(NBLOCKS, KLEV)

    ! output
    REAL(KIND=JPRB) PLUDE(NBLOCKS, KLEV)


    CALL vert_loop_7_no_klon_routine(&
        & KLEV, NCLV, KIDIA, KFDIA, NCLDQS, NCLDQI, NCLDQL, NCLDTOP, NBLOCKS, &
        & PTSPHY, RLMIN, ZEPSEC, RG, RTHOMO, ZALFAW, PLU, LDCUM, PSNDE, PAPH, PSUPSAT, PT, tendency_tmp_T, &
        & PLUDE)

END PROGRAM
! Base on lines 1096 to 1120 and others
SUBROUTINE vert_loop_7_no_klon_routine(&
    & KLEV, NCLV, KIDIA, KFDIA, NCLDQS, NCLDQI, NCLDQL, NCLDTOP, NBLOCKS, &
    & PTSPHY, RLMIN, ZEPSEC, RG, RTHOMO, ZALFAW, PLU_NFS, LDCUM_NFS, PSNDE_NFS, PAPH_NFS, PSUPSAT_NFS, PT_NFS, tendency_tmp_t_NFS, &
    & PLUDE_NFS)

    INTEGER, PARAMETER :: JPIM = SELECTED_INT_KIND(9)
    INTEGER, PARAMETER :: JPRB = SELECTED_REAL_KIND(13, 300)

    ! Parameters
    INTEGER(KIND=JPIM) KLEV
    INTEGER(KIND=JPIM) NCLV
    INTEGER(KIND=JPIM) KIDIA 
    INTEGER(KIND=JPIM) KFDIA 
    INTEGER(KIND=JPIM) NCLDQS 
    INTEGER(KIND=JPIM) NCLDQI 
    INTEGER(KIND=JPIM) NCLDQL 
    INTEGER(KIND=JPIM) NCLDTOP
    INTEGER(KIND=JPIM) NBLOCKS 

    ! input
    REAL(KIND=JPRB) PTSPHY
    REAL(KIND=JPRB) RLMIN
    REAL(KIND=JPRB) ZEPSEC
    REAL(KIND=JPRB) RG
    ! was a temporary scalar before, to complicated to include whole computation here
    REAL(KIND=JPRB) ZALFAW
    REAL(KIND=JPRB) RTHOMO

    REAL(KIND=JPRB) PLU_NFS(NBLOCKS, KLEV)
    INTEGER(KIND=JPIM) LDCUM_NFS(NBLOCKS)
    REAL(KIND=JPRB) PSNDE_NFS(NBLOCKS, KLEV)
    REAL(KIND=JPRB) PAPH_NFS(NBLOCKS, KLEV+1)
    ! This could be different in memory
    REAL(KIND=JPRB) PSUPSAT_NFS(NBLOCKS, KLEV)
    REAL(KIND=JPRB) PT_NFS(NBLOCKS, KLEV)
    REAL(KIND=JPRB) tendency_tmp_t_NFS(NBLOCKS, KLEV)

    ! output
    REAL(KIND=JPRB) PLUDE_NFS(NBLOCKS, KLEV)

    DO JN=1,NBLOCKS
        CALL inner_loops(&
            & KLEV, NCLV, KIDIA, KFDIA, NCLDQS, NCLDQI, NCLDQL, NCLDTOP, &
            & PTSPHY, RLMIN, ZEPSEC, RG, RTHOMO, ZALFAW, PLU_NFS(JN,:), LDCUM_NFS(JN), PSNDE_NFS(JN,:), PAPH_NFS(JN,:), &
            & PSUPSAT_NFS(JN,:), PT_NFS(JN,:), tendency_tmp_t_NFS(JN,:), &
            & PLUDE_NFS(JN,:))

    ENDDO

END SUBROUTINE vert_loop_7_no_klon_routine

SUBROUTINE inner_loops(&
    & KLEV, NCLV, KIDIA, KFDIA, NCLDQS, NCLDQI, NCLDQL, NCLDTOP, &
    & PTSPHY, RLMIN, ZEPSEC, RG, RTHOMO, ZALFAW, PLU_NFS, LDCUM_NFS, PSNDE_NFS, PAPH_NFS, PSUPSAT_NFS, PT_NFS, tendency_tmp_t_NFS, &
    & PLUDE_NFS)

    INTEGER, PARAMETER :: JPIM = SELECTED_INT_KIND(9)
    INTEGER, PARAMETER :: JPRB = SELECTED_REAL_KIND(13, 300)

    REAL(KIND=JPRB) PTSPHY
    REAL(KIND=JPRB) RLMIN
    REAL(KIND=JPRB) ZEPSEC
    REAL(KIND=JPRB) RG
    ! was a temporary scalar before, to complicated to include whole computation here
    REAL(KIND=JPRB) ZALFAW
    REAL(KIND=JPRB) RTHOMO
    REAL(KIND=JPRB) PLU_NFS(KLEV)
    LOGICAL LDCUM_NFS
    REAL(KIND=JPRB) PSNDE_NFS(KLEV)
    REAL(KIND=JPRB) PAPH_NFS(KLEV+1)
    ! This could be different in memory
    REAL(KIND=JPRB) PSUPSAT_NFS(KLEV)
    REAL(KIND=JPRB) PT_NFS(KLEV)
    REAL(KIND=JPRB) tendency_tmp_t_NFS(KLEV)

    ! output
    REAL(KIND=JPRB) PLUDE_NFS(KLEV)

    ! temporary scalars
    ! temporary arrays
    REAL(KIND=JPRB) ZCONVSRCE(NCLV)
    REAL(KIND=JPRB) ZSOLQA(NCLV, NCLV)
    REAL(KIND=JPRB) ZDTGDP
    REAL(KIND=JPRB) ZDP
    REAL(KIND=JPRB) ZGDP
    ! Cut away KLEV dimension of ZTP1
    REAL(KIND=JPRB) ZTP1

    ! Not sure if this causes problems
    ZCONVSRCE(:) = 0.0
    ZSOLQA(:, :) = 0.0
    ZDTGDP = 0.0
    ZDP = 0.0
    ZGDP = 0.0
    ZTP1 = 0.0

    DO JK=NCLDTOP,KLEV
        ZTP1        = PT_NFS(JK)+PTSPHY*tendency_tmp_t_NFS(JK)
        ! Loop from line 1061
        IF (PSUPSAT_NFS(JK)>ZEPSEC) THEN
            IF (ZTP1 > RTHOMO) THEN
                ZSOLQA(NCLDQL,NCLDQL) = ZSOLQA(NCLDQL,NCLDQL)+PSUPSAT_NFS(JK)
            ELSE
                ZSOLQA(NCLDQI,NCLDQI) = ZSOLQA(NCLDQI,NCLDQI)+PSUPSAT_NFS(JK)
            ENDIF
        ENDIF

        ZDP     = PAPH_NFS(JK+1)-PAPH_NFS(JK)     ! dp
        ZGDP    = RG/ZDP                    ! g/dp
        ZDTGDP  = PTSPHY*ZGDP               ! dt g/dp

        PLUDE_NFS(JK)=PLUDE_NFS(JK)*ZDTGDP

        IF(LDCUM_NFS.AND.PLUDE_NFS(JK) > RLMIN.AND.PLU_NFS(JK+1)> ZEPSEC) THEN
            ZCONVSRCE(NCLDQL) = ZALFAW*PLUDE_NFS(JK)
            ZCONVSRCE(NCLDQI) = (1.0 - ZALFAW)*PLUDE_NFS(JK)
            ZSOLQA(NCLDQL,NCLDQL) = ZSOLQA(NCLDQL,NCLDQL)+ZCONVSRCE(NCLDQL)
            ZSOLQA(NCLDQI,NCLDQI) = ZSOLQA(NCLDQI,NCLDQI)+ZCONVSRCE(NCLDQI)
        ELSE

            PLUDE_NFS(JK)=0.0

        ENDIF
        ! *convective snow detrainment source
        IF (LDCUM_NFS) ZSOLQA(NCLDQS,NCLDQS) = ZSOLQA(NCLDQS,NCLDQS) + PSNDE_NFS(JK)*ZDTGDP

    ENDDO ! on vertical level JK

END SUBROUTINE inner_loops

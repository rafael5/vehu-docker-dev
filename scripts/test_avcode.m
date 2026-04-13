AVDBG ;Debug AVCODE passing issue
 ; Simulate exactly what CALLP+CAPI does for XUS AV CODE
 S U="^"
 ; Simulate what PRS5 does
 S XWB(5,"P",0)="fakedoc1;1Doc!@#$"
 S XWB("PARAM")=$NA(XWB(5,"P",0))
 W "XWB(""PARAM"") = ",XWB("PARAM"),!
 ; Simulate what CAPI does
 S XWB(2,"RTAG")="VALIDAV",XWB(2,"RNAM")="XUSRB"
 S PAR=XWB("PARAM")
 S XWBCALL=XWB(2,"RTAG")_"^"_XWB(2,"RNAM")_"(.XWBY"_$S($L(PAR):","_PAR,1:"")_")"
 W "XWBCALL = ",XWBCALL,!
 W "XWB(5,""P"",0) = ",XWB(5,"P",0),!
 ; Now simulate the D @XWBCALL — call TEST instead of VALIDAV
 W "Calling with D @XWBCALL...",!
 S $ETRAP="W ""ERROR: "",$ZERROR,! H"
 D @("TST(.XWBY,"_$NA(XWB(5,"P",0))_")")
 W "XWBY(0) = ",$G(XWBY(0)),!
 Q
TST(RET,AVCODE) ;stand-in for VALIDAV
 W "  In TST: AVCODE defined? ",$D(AVCODE),!
 I $D(AVCODE) W "  AVCODE = ",AVCODE,!
 E  W "  AVCODE is UNDEFINED",!
 S RET(0)="ok"
 Q

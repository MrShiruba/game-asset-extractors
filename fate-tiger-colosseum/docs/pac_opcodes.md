# PAC command list

Generated from `EBOOT.BIN`: names from the command registration tables (file offsets 0xF906C–0xFAC18),
argument layouts from the operand reads done by each command's handler.
The instruction marker is `25 GG OO 00`: GG = group, OO = index below.

Argument codes: **typed** = 1 type byte, padding to 4, 32-bit value (see operand types in
[`formats.md`](formats.md)); **u32 / u16 / u8** = raw value; **string** = inline null-terminated
Shift-JIS; a `…Label` command's u32 is the offset of a string in the string pool.

## Group 0 — core

| OO | Command | Arguments |
|---|---|---|
| 0x00 | `null` | — |
| 0x01 | `cmd_end` | — |
| 0x02 | `cmd_jmp` | u32 |
| 0x03 | `cmd_call` | u32 |
| 0x04 | `cmd_result` | typed |
| 0x05 | `cmd_resJmp` | typed, u32 |
| 0x06 | `cmd_resCall` | typed, u32 |
| 0x07 | `cmd_mov` | typed, typed |
| 0x08 | `cmd_add` | typed, typed |
| 0x09 | `cmd_sub` | typed, typed |
| 0x0A | `cmd_mul` | typed, typed |
| 0x0B | `cmd_div` | typed, typed |
| 0x0C | `cmd_inc` | typed |
| 0x0D | `cmd_dec` | typed |
| 0x0E | `cmd_loop` | typed, u32 |
| 0x0F | `cmd_waitFrame` | typed |
| 0x10 | `cmd_waitTime` | typed |
| 0x11 | `cmd_rand` | typed, typed |
| 0x12 | `cmd_iand` | typed, typed |
| 0x13 | `cmd_ior` | typed, typed |
| 0x14 | `cmd_ixor` | typed, typed |
| 0x15 | `cmd_ifEQ` | typed, typed, u32 |
| 0x16 | `cmd_ifNE` | typed, typed, u32 |
| 0x17 | `cmd_ifLSE` | typed, typed, u32 |
| 0x18 | `cmd_ifLBE` | typed, typed, u32 |
| 0x19 | `cmd_ifLS` | typed, typed, u32 |
| 0x1A | `cmd_ifLB` | typed, typed, u32 |
| 0x1B | `cmd_ifAND` | typed, typed, u32 |
| 0x1C | `cmd_ifOR` | typed, typed, u32 |
| 0x1D | `cmd_ifCallEQ` | typed, typed, u32 |
| 0x1E | `cmd_ifCallNE` | typed, typed, u32 |
| 0x1F | `cmd_ifCallLSE` | typed, typed, u32 |
| 0x20 | `cmd_ifCallLBE` | typed, typed, u32 |
| 0x21 | `cmd_ifCallLS` | typed, typed, u32 |
| 0x22 | `cmd_ifCallLB` | typed, typed, u32 |
| 0x23 | `cmd_ifCallAND` | typed, typed, u32 |
| 0x24 | `cmd_ifCallOR` | typed, typed, u32 |
| 0x25 | `cmd_flgSet` | u8, u32 |
| 0x26 | `cmd_flgClr` | u8, u32 |
| 0x27 | `cmd_flgSetId` | typed |
| 0x28 | `cmd_flgClrId` | typed |
| 0x29 | `cmd_flgMov` | u32, u32 |
| 0x2A | `cmd_flgAND` | u32, u8, u32 |
| 0x2B | `cmd_flgOR` | u32, u8, u32 |
| 0x2C | `cmd_flgZERO` | u32, u8, u32 |
| 0x2D | `cmd_inxJmp` | typed index, then a table of u32 jump offsets |
| 0x2E | `cmd_stkDec` | — |
| 0x2F | `cmd_stkClr` | — |
| 0x30 | `cmd_break` | typed, string |
| 0x31 | `cmd_string` | string |
| 0x32 | `cmd_print` | string, typed |
| 0x33 | `cmd_textOut` | typed |
| 0x34 | `cmd_setSleep` | typed |
| 0x35 | `cmd_sinf` | typed, typed |
| 0x36 | `cmd_cosf` | typed, typed |
| 0x37 | `cmd_abs` | typed, typed |
| 0x38 | `cmd_setLabelId` | typed, u32 |
| 0x39 | `cmd_callLabelId` | typed |
| 0x3A | `cmd_jmpLabelId` | typed |
| 0x3B | `cmd_mod` | typed, typed |
| 0x3C | `cmd_memset` | typed, typed, typed |
| 0x3D | `cmd_memcpy` | typed, typed, typed |
| 0x3E | `cmd_flgMemcpy` | typed, typed, typed |
| 0x3F | `cmd_stringEnable` | typed |

## Group 1 — message

| OO | Command | Arguments |
|---|---|---|
| 0x00 | `null` | — |
| 0x01 | `setCurrentWindow` | typed |
| 0x02 | `setWindowPosition` | typed, typed |
| 0x03 | `setWindowName` | string, typed, typed, typed, typed, typed |
| 0x04 | `setWindowNameLabel` | u32, typed, typed, typed, typed, typed |
| 0x05 | `setTextOffset` | typed, typed |
| 0x06 | `showWindow` | typed |
| 0x07 | `setFontScale` | typed, typed |
| 0x08 | `setFontColor` | typed |
| 0x09 | `waitMessage` | typed |
| 0x0A | `setWindowZ` | typed |
| 0x0B | `waitPause` | — |
| 0x0C | `showPuaseSymbol` | — |
| 0x0D | `setMessage` | string |
| 0x0E | `setMessageLabel` | u32 |
| 0x0F | `clearMessage` | — |
| 0x10 | `loadWindowModel` | typed, typed |
| 0x11 | `setWindowMotion` | typed, typed |
| 0x12 | `enableMotionLoop` | typed |
| 0x13 | `playVoice` | typed |
| 0x14 | `loadVoice` | typed |
| 0x15 | `clearVoice` | — |
| 0x16 | `waitVoice` | typed |
| 0x17 | `playBGM` | typed |
| 0x18 | `loadBGM` | typed |
| 0x19 | `clearBGM` | — |
| 0x1A | `releaseCache` | — |
| 0x1B | `waitWindowModel` | typed |
| 0x1C | `clearWindowModel` | typed |
| 0x1D | `fadeMasterVolume` | typed, typed |
| 0x1E | `fadeBGMVolume` | typed, typed |
| 0x1F | `fadeVoiceVolume` | typed, typed |
| 0x20 | `moveWindow` | typed, typed, typed |
| 0x21 | `stopBGM` | — |
| 0x22 | `waitBGMVolume` | typed |
| 0x23 | `setFontCharacterSeparation` | typed |
| 0x24 | `setFontInterlinearSpace` | typed |
| 0x25 | `setWindowModelColor` | typed, typed |
| 0x26 | `setWindowModelColorAnimation` | typed, typed, typed |
| 0x27 | `waitWindowModelColorAnimation` | — |
| 0x28 | `setMoveWindow` | typed, typed, typed, typed |
| 0x29 | `waitMoveWindow` | typed |
| 0x2A | `waitAllMoveWindow` | — |
| 0x2B | `setWindowScale` | typed |
| 0x2C | `isShowWindow` | typed |
| 0x2D | `hideWindows` | typed |
| 0x2E | `revertHideWindows` | — |
| 0x2F | `playSE` | typed, typed, typed, typed |
| 0x30 | `loadSE` | typed |
| 0x31 | `clearSE` | — |
| 0x32 | `waitSEAll` | — |
| 0x33 | `waitSE` | typed |
| 0x34 | `getLastPlaySEVoiceChannel` | typed |
| 0x35 | `stopSEAll` | — |
| 0x36 | `stopSE` | typed |
| 0x37 | `fadeSEVolume` | typed, typed, typed |
| 0x38 | `waitSEVolume` | typed, typed |
| 0x39 | `setTextSpeed` | typed |
| 0x3A | `waitPauseEx` | typed, typed |
| 0x3B | `setAutoPlay` | typed, typed |
| 0x3C | `resetTimer` | — |
| 0x3D | `waitTimer` | typed |
| 0x3E | `playVoiceEx` | typed, typed |
| 0x3F | `playBGMEx` | typed, typed, typed |
| 0x40 | `setVoiceVolume` | typed |
| 0x41 | `setBGMVolume` | typed |
| 0x42 | `autoSave` | — |
| 0x43 | `autoLoad` | — |
| 0x44 | `addOptionMenuItem` | string, u32, typed |
| 0x45 | `setOptionMenuItem` | string, u32, typed, typed |
| 0x46 | `clearOptionMenu` | — |
| 0x47 | `enableOptionMenu` | typed |
| 0x48 | `addMsgWindowItem` | string |
| 0x49 | `setMsgWindowItem` | string, typed |
| 0x4A | `clearMsgWindow` | — |
| 0x4B | `enableMsgWindow` | typed |
| 0x4C | `setOptionCancelLabel` | u32 |
| 0x4D | `setMsgWindowForm` | typed, typed, typed, typed |
| 0x4E | `powerSaveOff` | typed |
| 0x4F | `getOptionState` | typed |
| 0x50 | `getTimer` | typed |
| 0x51 | `setCancelVoice` | typed |

## Group 2 — menu

| OO | Command | Arguments |
|---|---|---|
| 0x00 | `null` | — |
| 0x01 | `padDirect` | typed |
| 0x02 | `padStand` | typed |
| 0x03 | `padRepeat` | typed |
| 0x04 | `registToMenu` | string, u32 |
| 0x05 | `selectMenuItemCall` | typed, u32 |
| 0x06 | `selectMenuItemJmp` | typed, u32 |
| 0x07 | `memoryPrint` | — |
| 0x08 | `setMenuPos` | typed, typed, typed |
| 0x09 | `padRelease` | typed |

## Group 3 — GameSystemCommand

| OO | Command | Arguments |
|---|---|---|
| 0x00 | `null` | — |
| 0x01 | `changeState` | typed |
| 0x02 | `getCharacterID` | typed |
| 0x03 | `getCostumeID` | typed |
| 0x04 | `playSystemSE` | typed |
| 0x05 | `setCostumeID` | typed |
| 0x06 | `setStageID` | typed, typed |
| 0x07 | `getCharacterCount` | typed |
| 0x08 | `getCharacterParam` | typed, typed, typed, typed |
| 0x09 | `setWinner` | typed |
| 0x0A | `setRule` | typed |
| 0x0B | `setPointLimit` | typed |
| 0x0C | `setTimeLimit` | typed |
| 0x0D | `getBattleMode` | typed |
| 0x0E | `setVersusCharacter` | typed, typed, typed |
| 0x0F | `setVersusRule` | typed, typed |
| 0x10 | `setVersusRuleMessage` | string |
| 0x11 | `setVersusRuleMessageLabel` | u32 |
| 0x12 | `setVersusStageID` | typed, typed |
| 0x13 | `setVersusClear` | — |
| 0x14 | `setVersusPoint` | typed |
| 0x15 | `getUserDifficulty` | typed |
| 0x16 | `doContinue` | typed |
| 0x17 | `setBattleBgm` | typed |

## Group 4 — CharacterSetup

| OO | Command | Arguments |
|---|---|---|
| 0x00 | `null` | — |
| 0x01 | `setAlpha` | typed, typed |
| 0x02 | `setVoiceTiming` | typed, typed, typed, typed |
| 0x03 | `setBlurEffectTiming` | typed, typed, typed, typed, typed, typed, typed, typed, typed |
| 0x04 | `setVirtualBoneId` | typed, typed |
| 0x05 | `getCostumeId` | typed |
| 0x06 | `createAttackInfo` | typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed |
| 0x07 | `setAttackTiming` | typed, typed, typed, typed, typed, typed |
| 0x08 | `createGuardInfo` | typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed |
| 0x09 | `setGuardTiming` | typed, typed, typed, typed, typed |
| 0x0A | `setSystemEffectTimingPlayFixCharacterPosition` | typed, typed, typed, typed, typed, typed |
| 0x0B | `setSystemEffectTimingPlayCharacterPosition` | typed, typed, typed, typed, typed, typed |
| 0x0C | `setSystemEffectTimingPlayFixCharacterBonePosition` | typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed |
| 0x0D | `setSystemEffectTimingPlayCharacterBonePosition` | typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed |
| 0x0E | `setStatus` | typed, typed, typed, typed, typed, typed, typed, typed |
| 0x0F | `setCharacterEffectTimingPlayFixCharacterPosition` | typed, typed, typed, typed, typed, typed |
| 0x10 | `setCharacterEffectTimingPlayCharacterPosition` | typed, typed, typed, typed, typed, typed |
| 0x11 | `setCharacterEffectTimingPlayFixCharacterBonePosition` | typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed |
| 0x12 | `setCharacterEffectTimingPlayCharacterBonePosition` | typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed |
| 0x13 | `setSpeed` | typed, typed, typed, typed |
| 0x14 | `fire` | typed, typed, typed, typed, typed |
| 0x15 | `setCharacterTextureCrop` | typed, typed, typed, typed, typed, typed, typed, typed |
| 0x16 | `createCharacterTextureCropLayer` | typed |
| 0x17 | `setShowStageTiming` | typed, typed, typed, typed, typed, typed |
| 0x18 | `setSeTiming` | typed, typed, typed, typed, typed |
| 0x19 | `setVirtualMaterialId` | typed, typed |
| 0x1A | `setCounterbalanceTiming` | typed, typed, typed, typed, typed, typed, typed, typed, typed |
| 0x1B | `setBasePersonality` | u32 |
| 0x1C | `setRandomVoiceTiming` | typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed |
| 0x1D | `lookAtMe` | typed, typed, typed, typed |
| 0x1E | `directionCamera` | typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed |
| 0x1F | `setExtendPersonality` | u32, u32 |
| 0x20 | `setSeTimingOneShot` | typed, typed, typed, typed |
| 0x21 | `setVoiceTimingOneShot` | typed, typed, typed, typed |
| 0x22 | `setRandomVoiceTimingOneShot` | typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed, typed |
| 0x23 | `setDifficultyCorrectionValue` | typed, typed, typed, typed, typed, typed |
| 0x24 | `setSeTimingEx` | typed, typed, typed, typed, typed, typed |

## Group 5 — StageSetup

| OO | Command | Arguments |
|---|---|---|
| 0x00 | `null` | — |
| 0x01 | `setAlpha` | typed, typed |
| 0x02 | `addNpc` | typed, typed, typed, typed, typed |
| 0x03 | `setCharacterColor` | typed |
| 0x04 | `setItemAppearancePointCount` | typed |
| 0x05 | `setItemInfoCount` | typed |
| 0x06 | `setItemAppearancePoint` | typed, typed, typed, typed, typed, typed |
| 0x07 | `addItemInfo` | typed, typed, typed |
| 0x08 | `setMaxActiveItemCount` | typed |
| 0x09 | `addItemResource` | typed, typed, typed, typed, typed, typed |
| 0x0A | `setStageModelMotion` | typed |
| 0x0B | `setStageSubModelMotion` | typed |
| 0x0C | `addInitilizePosition` | typed, typed, typed, typed |
| 0x0D | `setMapNodeMax` | u32, u32, u32, u32 |
| 0x0E | `appendNode` | u32, u32, u32, u32, u32, u32 |
| 0x0F | `connectLink` | u32, u32, u32 |
| 0x10 | `getDayTime` | typed |
| 0x11 | `addEvent` | u32, u32, u32, u32, u32 |
| 0x12 | `addSphereEventSwitch` | u32, u32, u32, u32, u32, u32, u32, u32 |
| 0x13 | `setItemAppearancePointOption` | typed, typed, typed, typed, typed, typed |
| 0x14 | `addCylinderEventSwitch` | u32, u32, u32, u32, u32, u32, u32, u32, u32, u32, u32 |

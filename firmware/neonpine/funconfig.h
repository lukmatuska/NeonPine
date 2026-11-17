#ifndef _FUNCONFIG_H
#define _FUNCONFIG_H

#define FUNCONF_USE_DEBUGPRINTF  0  // SWIO stays free; status goes over USB (../tools/npctl.py)
#define FUNCONF_SYSTICK_USE_HCLK 1  // required by rv003usb; SysTick->CNT counts at 48 MHz

#endif

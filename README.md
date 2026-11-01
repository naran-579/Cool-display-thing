# Cool display thing

This is a little matrix project that stands upright on your desk and can display whatever you want it to, all customizable with a GUI
<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/d09df421-3f16-4e78-a391-7d346dd3ed69" />
<img width="896" height="773" alt="image" src="https://github.com/user-attachments/assets/22188c01-b504-4d76-b7e7-e9b1d94ede50" />


# How to build

1. Obtain the parts from BOM.CSV
2. Solder said parts onto the PCB
3. Install Micropython on the RP2040
4. Put the firmware from /firmware/Cool Matrix display thing/firmware onto the board
5. Customize the message using /firmware/Cool Matrix display thing/Matrix Studio.py
6. Everything should work


# the button

|Action               |Playlist             |Timer                      |Stopwatch                  |
|---------------------|---------------------|---------------------------|---------------------------|
|Press                |Skip to the next item|Start or pause             |Start or pause             |
|Double-press         |Same as press        |Reset to the starting time |Reset to 00:00             |
|Hold (about 1 second)|Switch to the timer  |Switch to the stopwatch    |Switch back to the playlist|
|Press while flashing |-                    |Stop the flashing and reset|-                          |



# BOM


|Item                    |Qty|Supplier           |Cost/item|Total Cost|link                                                                                                                                                                                                                                                                                                                                                                         |
|------------------------|---|-------------------|---------|----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|XIAO RP2040             |1  |SEEED              |$4.99    |$4.99     |https://www.seeedstudio.com/Seeed-Studio-XIAO-RP2040-Pre-Soldered-p-6333.html                                                                                                                                                                                                                                                                                                |
|FC16 4-in-1 matrix      |1  |DIYables via amazon|$7.99    |$7.99     |https://www.amazon.com/dp/B0BXKKT72V?lv=shuf&channelId=520&plpRedirect=mhFallback                                                                                                                                                                                                                                                                                            |
|MAtrix headers          |1  |Digikey            |$0.44    |$0.44     |https://www.digikey.com/en/products/detail/sullins-connector-solutions/PPTC051LFBN-RC/807239                                                                                                                                                                                                                                                                                 |
|Clock Module headers    |1  |Digikey            |$0.47    |$0.47     |https://www.digikey.com/en/products/detail/sullins-connector-solutions/PPTC061LFBN-RC/810145                                                                                                                                                                                                                                                                                 |
|Button                  |1  |Digikey            |$0.58    |$0.58     |https://www.digikey.com/en/products/detail/schurter-inc/1301-9302/7602712                                                                                                                                                                                                                                                                                                    |
|Capacitor               |1  |Digikey            |$0.79    |$0.79     |https://www.digikey.com/en/products/detail/rubycon/450BXC10MEFC10X20/3563744                                                                                                                                                                                                                                                                                                 |
|DS3231 clock module     |1  |DORHEA via amazon  |$9.99    |$9.99     |https://www.amazon.com/DS3231-AT24C32-Module-Memory-Replace/dp/B09LLMYBM1/ref=pd_ci_mcx_di_int_sccai_cn_d_sccl_1_1/130-2453352-8957139?pd_rd_w=NdFSs&content-id=amzn1.sym.751acc83-5c05-42d0-a15e-303622651e1e&pf_rd_p=751acc83-5c05-42d0-a15e-303622651e1e&pf_rd_r=X0E8Y4E023VWVK4KATNV&pd_rd_wg=uQctI&pd_rd_r=0f8a02a8-57f9-460a-b512-3222eed9eb0f&pd_rd_i=B09LLMYBM1&psc=1|
|PCB                     |1  |JLCPCB             |$5.10    |$5.10     |https://cart.jlcpcb.com/quote?stencilLayer=2&stencilWidth=100&stencilLength=100&stencilCounts=5&plateType=1&spm=Jlcpcb.Homepage.1010                                                                                                                                                                                                                                         |
|Estimated total shipping|1  |                   |         |$0.00     |                                                                                                                                                                                                                                                                                                                                                                             |

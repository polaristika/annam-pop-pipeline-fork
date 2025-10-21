## Small Guide to Making Nice Tables

Markus Püschel Carnegie Mellon University www.ece.cmu.edu/~pueschel

## Which One Looks Better?

| signal processing concept                                        | algebraic concept (coordinate free                      | in coordinates                |
|------------------------------------------------------------------|---------------------------------------------------------|-------------------------------|
| fi signal fi Itering impulse impulse response of h € A Iter      | (algebra) (A-module) h . s vector bi € M h . bi€ M base | 5 = %(h) . s b;i = = ho, h _1 |
| Fourier transform spectrum of signal frequency response of h € A | 4(s) = (sw)wew @vew                                     | 4 $ =                         |

| signal processing concept                                                                                                  | algebraic concept (coordinate free)                                              | in coordinates                                                          |
|----------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| filter signal impulse impulse response of h € .A Fourier transfor spectrum of signal frequency response of h € A filtering | h €.A (algebra) (A-module) h base vector b; € M h . b; € M 4 : M = = W F 1.a. Sw | (si)iel bi F : cI _ 4 0 = @~ F(s) = (s)ew =W F SW =W F € CIxI € CI h_1. |

Easy decision, isn't it?

## Another One

| f   | f      | f   | Sn Sn -2            | Sn       | Sn        | Sn        |
|-----|--------|-----|---------------------|----------|-----------|-----------|
|     | 1      | T   | DCT-1               | DCT-3 Tn | DCT-5     | DCT-7     |
| =0  | sin 0  |     | DST-3 2Tn           | DST- Un  | DST-7 Vn  | DST-5 Wn  |
| s0  | 20     |     | DCT-6 2(2 ~ 1)Wn _1 | DCT-8 Vn | DCT-2     | DCT-4 2Tn |
|     | sin 20 |     | DST-8               | DST-6 Wn | DST-4 2Tn | DST-2     |

|           | Sn Sn=2            | Sn       | Sn Sn -1          | Sn + Sn_1           |        |    |
|-----------|--------------------|----------|-------------------|---------------------|--------|----|
|           | DCT-1 1)Un -2      | DCT-3 Tn | DCT-5 (z = 1)Wn_1 | DCT-7               |        | T  |
| 8 _1 =0   | DST-3 2Tn          | DST-1 Un | DST-7 Vn          | DST-5 Wn            | sin 0  |    |
| = s0 8 _1 | DCT-6 2( I)Wn _1   | DCT-8 Vn | DCT-2             | DCT-4 2Tn           | cOS    |    |
| ~s0       | DST-8 2(æ + I)Vn_1 | DST-6 Wn | DST-4 2Tn         | DST-2 2(æ + I)Un _1 | sin 20 | W  |

If your tables tend to look like the above you may find this guide helpful

## Background

-  Up to 2005, I had been writing technical publications for 8 years, creating roughly 35 fully reviewed papers, 2 theses, 20 proposals, and many other pages of technical writing
-  In each case I spent a lot of effort on content and visual presentation; I am really picky
-  In 2005 I learned (from Goran Frehse, thank you!) that I had had no clue how to make tables
-  I summarize what I have learned in this short guide

## Resources

-  'Chicago Manual of Style,' The University of Chicago Press
-  Latex users: Use booktabs.sty and its documentation http://texcatalogue.sarovar.org/entries/booktabs.html

## Most Important Guidelines for Making Tables

-  Avoid vertical lines
-  Avoid 'boxing up' cells, usually 3 horizontal lines are enough: above, below, and after heading (see examples in this guide)
-  Avoid double horizontal lines
-  Enough space between rows
-  If in doubt, align left

## Example: Before and After

## Before:

|                                                                                            | abstract    | realized                            |
|--------------------------------------------------------------------------------------------|-------------|-------------------------------------|
| shift operator shift operation space mark k-fold shift operator space shift signal fi Iter | 9 tn = Sntn | Cn 1 . Cn = 4(Cn+1 + Cn-1) SnCn (æ) |

also the first column gets a header

## After:

more space between rows

<!-- image -->

three horizontal lines only, I like the top and bottom ones bolder

<!-- image -->

everything left aligned

<!-- image -->

| concept                                                                                   | abstract                    | realized                                                  |
|-------------------------------------------------------------------------------------------|-----------------------------|-----------------------------------------------------------|
| shift operator shift operation space mark k-fold shift operator space shift signal filter | 9 tn Tk(q) = Sntn EhkTk (9) | T1(æ) =1 Cn Tk(æ) 1 Cn = 4(Cn+1 + Cn-1) SnCn (x) hkTk (æ) |

<!-- image -->

space to the left edge removed

<!-- image -->

## In Latex

-  Style: \usepackage{booktabs}
- 
- Horizontal lines: read documentation of booktabs http://texcatalogue.sarovar.org/entries/booktabs.html
-  More space between rows: \renewcommand{\arraystretch}{1.2} (or 1.3)
- 
- Remove space to the vertical edges: \begin{tabular}{@{}lll@{}} …

## Hierarchical Tables: Examples

## One level of hierarchy: x-axis only

## One level of hierarchy: x-axis and y-axis

|         | W = 8    | W = 8    | W = 8    | W = 16   | W = 16    | W = 16    | W = 32    | W = 32    | W = 32    |
|---------|----------|----------|----------|----------|-----------|-----------|-----------|-----------|-----------|
|         | twid = 0 | twid = 1 | twid = 2 | twid = 0 | twid = 1  | twid = 2  |           | twid = 1  | twid = 2  |
| dir = 1 |          |          |          |          |           |           |           |           |           |
|         | 0.0790   | 0.1692   | 0.2945   | 0.3670   | 0.7187    | 3.1815    | -1.0032   | -1.7104   | -21.7969  |
|         | -0.8651  | 50.0476  | 5.9384   | -9.0714  | 297.0923  | 46.2143   | 4.3590    | 34.5809   | 76.9167   |
| Ctop.   | 124.2756 | -50.9612 | -14.2721 | 128.2265 | -630.5455 | -381.0930 | -121.0518 | -137.1210 | -220.2500 |
| dir 0   |          |          |          |          |           |           |           |           |           |
| Crop `  | 0.0357   | 1.2473   | 0.2119   | 0.3593   |           | 2.1764    | -1.2998   |           | -1.2784   |
| Crop .  | -17.9048 | -37.1111 | 8.8591   | -30.7381 | -9.5952   | -3.0000   | -11.1631  | -5.7108   | -15.6728  |
|         | 105.5518 | 232.1160 | -94.7351 | 100.2497 | 141.2778  | -259.7326 | 52.5745   | 10.1098   | -140.2130 |

| slices      |     |      | abs. error (slices)   | abs. error (slices)   |
|-------------|-----|------|-----------------------|-----------------------|
|             | avg | max. | avg                   | max                   |
| 5000        | 7.4 | 73.5 | 116                   | 625                   |
| 5000-10000  | 3.1 | 27.2 | 209                   | 1807                  |
| 10000-15000 | 2.4 | 15.6 | 297                   | 2133                  |
| 15000       | 1.8 | 9.0  | 317                   | 1609                  |

## Latex Example

## Table from the bottom of the previous slide:

```
\usepackage{booktabs} \newcommand{\ra}[1]{\renewcommand{\arraystretch}{#1}} \begin{table*}\centering \ra{1.3} \begin{tabular}{@{}rrrrcrrrcrrr@{}}\toprule & \multicolumn{3}{c}{$w = 8$} & \phantom{abc}& \multicolumn{3}{c}{$w = 16$} & \phantom{abc} & \multicolumn{3}{c}{$w = 32$}\\ \cmidrule{2-4} \cmidrule{6-8} \cmidrule{10-12} & $t=0$ & $t=1$ & $t=2$ && $t=0$ & $t=1$ & $t=2$ && $t=0$ & $t=1$ & $t=2$\\ \midrule $dir=1$\\ $c$ & 0.0790 & 0.1692 & 0.2945 && 0.3670 & 0.7187 & 3.1815 && -1.0032 & -1.7104 & -21.7969\\ $c$ &  -0.8651& 50.0476& 5.9384&& -9.0714& 297.0923& 46.2143&& 4.3590& 34.5809& 76.9167\\ $c$ & 124.2756& -50.9612& -14.2721&& 128.2265& -630.5455& -381.0930&& -121.0518& -137.1210& -220.2500\\ $dir=0$\\ $c$ & 0.0357& 1.2473& 0.2119&& 0.3593& -0.2755& 2.1764&& -1.2998& -3.8202& -1.2784\\ $c$ & -17.9048& -37.1111& 8.8591&& -30.7381& -9.5952& -3.0000&& -11.1631& -5.7108& -15.6728\\ $c$ & 105.5518& 232.1160& -94.7351&& 100.2497& 141.2778& -259.7326&& 52.5745& 10.1098& -140.2130\\ \bottomrule \end{tabular} \caption{Caption} \end{table*}
```

## Further Examples

-  The following tables are taken from the magazine Economist
-  They demonstrate
-  How to handle multiple levels of hierarchy
-  Alignment, handling of long headers
-  The use of light gray to further divide the tables
-  Horizontal lines provide readability under denser packing and when lots of numbers are organized
-  Sans serif fonts are preferrable for readability; of course, if you need math symbols and use latex, then stick with roman
-  Title above table, sometimes with unit of measure
-  The use of footnotes
-  Different types of horizontal lines (I personally don't like the use of more than two)

## Example Tables I

| Price of privilege Minimum wealth required to be in: 2000, $   | 2,161   | 109 Top   | 61,041   |
|----------------------------------------------------------------|---------|-----------|----------|
| 50% 40% Top Top                                                | 3,517   | 5% Top    | 150,145  |
| 30% Top                                                        | 6,318   | 1% Top    | 514,512  |
| Top 20%                                                        | 14,169  |           |          |

## Not enough

Women as % of German newspapers'

|                                | readers in 2006   | editorial positions top   |
|--------------------------------|-------------------|---------------------------|
| Dailies                        |                   |                           |
| Süddeutsche Zeitung            | 44.0              | 10.0                      |
| Frankfurter Allgemeine Zeitung | 36.0              | 6.25                      |
| Handelsblatt                   | 25.0              |                           |
| Die Welt                       | 37.0              | 31.0                      |
| FT Deutschland                 | 32.0              | 25.0                      |
| Weeklies                       |                   |                           |
| Der Spiegel                    | 36.0              |                           |
| Focus                          | 36.0              | 16                        |
| Stern                          | 48.0              | 16.0                      |
| Die Zeit                       | 43.0              | 16.6                      |
| Wirtschaftswoche               | 20.5              |                           |

Sources: Medier-Analyse ag.ma; Newspapems; The Economist

|               | Latest on a   | 03 2006 year earlier   | 1997-2006   |
|---------------|---------------|------------------------|-------------|
| Denmark       | 23.3          | 18.7                   | 115         |
| Ireland       | 14.2          | 6.2                    | 252         |
| Canada        | 12.8          | 4.3                    | 69          |
| South Africa  | 12.7          | 20.7                   | 327         |
| France        | 12.5          | 15.5                   | 127         |
| Sweden        | 12.0          | 9.5                    | 123         |
| Belgium       | 11.8          | 20.0                   | 118         |
| Spain         | 10.8          | 13.4                   | 173         |
| New Zealand   | 9.6           | 14.9                   | 94          |
| Australia     | 9.5           | 1.7                    | 132         |
| Britain       | 9.6           | 2.7                    | 192         |
| United States | 7             | 12.7                   | 100         |
| Singapore     | 7.6           | 3.3                    | na          |
| Italy         | 6.6           | 7.3                    | 88          |
| Netherlands   | 6.2           | 5.3                    | 97          |
| China         | 5.4           | 5.5                    | na          |
| Switzerland   | 2.0           | 0.8                    | 16          |
| Germany       | 0.8           |                        |             |
| Hong Kong     | ~2.1          | 20.3                   |             |
| Japan         | 2.7           | 5.4                    | -32         |

## Example Tables II

## Democratic revival

Which ofthe following statements do you agree with most? %

|                | Democracy is preferable to any other type of government   | Democracy is preferable to any other type of government   | Democracy is preferable to any other type of government   |   Democracy is preferable to any other type of government | Democracy is preferable to any other type of government   | In certain circumstances an authoritarian government can be preferable to a democratic one   | In certain circumstances an authoritarian government can be preferable to a democratic one   | In certain circumstances an authoritarian government can be preferable to a democratic one   | In certain circumstances an authoritarian government can be preferable to a democratic one   | In certain circumstances an authoritarian government can be preferable to a democratic one   |
|----------------|-----------------------------------------------------------|-----------------------------------------------------------|-----------------------------------------------------------|-----------------------------------------------------------|-----------------------------------------------------------|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
|                | 1996                                                      | 2001                                                      | 2005                                                      |                                                      2006 | Change since 2005                                         | 1996                                                                                         | 2001                                                                                         | 2005                                                                                         | 2006                                                                                         | Change since 2005                                                                            |
| Uruguay        | 80                                                        | 79                                                        | 77                                                        |                                                        77 | nil                                                       |                                                                                              | 10                                                                                           | 10                                                                                           | 10                                                                                           |                                                                                              |
| Costa Rica     | 80                                                        |                                                           | 73                                                        |                                                        75 |                                                           |                                                                                              |                                                                                              |                                                                                              |                                                                                              |                                                                                              |
| Argentina      | 71                                                        | 58                                                        | 66                                                        |                                                        74 |                                                           | 15                                                                                           | 21                                                                                           | 17                                                                                           | 16                                                                                           |                                                                                              |
| Dominican Rep. | na                                                        | na                                                        | 60                                                        |                                                        71 | 11                                                        | na                                                                                           | na                                                                                           | 15                                                                                           | 21                                                                                           |                                                                                              |
| Venezuela      | 62                                                        | 57                                                        | 78                                                        |                                                        70 |                                                           | 19                                                                                           | 20                                                                                           | 11                                                                                           | 11                                                                                           |                                                                                              |
| Bolivia        | 64                                                        | 54                                                        | 49                                                        |                                                        62 |                                                           | 17                                                                                           | 17                                                                                           | 19                                                                                           | 19                                                                                           |                                                                                              |
| Chile          | 54                                                        | 45                                                        | 59                                                        |                                                        56 |                                                           | 19                                                                                           | 19                                                                                           | 11                                                                                           | 13                                                                                           |                                                                                              |
| Nicaragua      | 59                                                        | 43                                                        | 57                                                        |                                                        56 |                                                           | 14                                                                                           | 22                                                                                           | 10                                                                                           | 14                                                                                           |                                                                                              |
| Fanama         | 75                                                        | 34                                                        | 52                                                        |                                                        55 |                                                           | 10                                                                                           | 23                                                                                           | 12                                                                                           | 19                                                                                           |                                                                                              |
| Peru           | 63                                                        | 62                                                        | Lo                                                        |                                                        55 | 15                                                        | 13                                                                                           | 12                                                                                           | 19                                                                                           | 20                                                                                           |                                                                                              |
| Ecuador        | 52                                                        | 40                                                        | 43                                                        |                                                        54 | 11                                                        | 18                                                                                           | 23                                                                                           | 18                                                                                           | 21                                                                                           |                                                                                              |
| Mexico         | 53                                                        | 46                                                        | 59                                                        |                                                        54 |                                                           | 23                                                                                           | 35                                                                                           | 13                                                                                           | 15                                                                                           |                                                                                              |
| Colombia       | 60                                                        | 36                                                        | 46                                                        |                                                        53 |                                                           | 20                                                                                           | 16                                                                                           | 11                                                                                           | 15                                                                                           |                                                                                              |
| El Salvador    | 56                                                        | 25                                                        | 59                                                        |                                                        51 |                                                           | 12                                                                                           | 10                                                                                           |                                                                                              | 15                                                                                           |                                                                                              |
| Honduras       | 42                                                        | 57                                                        | 33                                                        |                                                        51 | 18                                                        | 14                                                                                           |                                                                                              | 10                                                                                           | 12                                                                                           |                                                                                              |
| Brazil         | 50                                                        | 30   37                                                   |                                                           |                                                        46 |                                                           | 24                                                                                           | 18                                                                                           | 15                                                                                           | 18                                                                                           |                                                                                              |
| Guatemala      | 50                                                        | 33                                                        | 32                                                        |                                                        41 |                                                           |                                                                                              | 21   21                                                                                      | 17                                                                                           | 35                                                                                           | 18                                                                                           |
| Paraguay       |                                                           | 59   35   32                                              |                                                           |                                                        41 |                                                           |                                                                                              |                                                                                              |                                                                                              | 30                                                                                           |                                                                                              |

Source: Latinobarómetro

| Trade, exchange rates, budget balances and interest rates   | Trade balance latest 12 months , Sbn   |                                               |                 |                       |                       | Buldgee % of GDP 2007+   | Interest rates, %   | Interest rates, %          |
|-------------------------------------------------------------|----------------------------------------|-----------------------------------------------|-----------------|-----------------------|-----------------------|--------------------------|---------------------|----------------------------|
|                                                             | Trade balance latest 12 months , Sbn   | Current-account balance latest 12 months, Sbn | 96 of GDP 2007t | Currency units, per $ | Currency units, per $ | Buldgee % of GDP 2007+   | 3-month latest      | 10-year govt bonds, latest |
|                                                             | Trade balance latest 12 months , Sbn   | Current-account balance latest 12 months, Sbn | 96 of GDP 2007t | Jan 1Oth              | year ago              | Buldgee % of GDP 2007+   | 3-month latest      | 10-year govt bonds, latest |
| United States                                               |                                        | 880.3 03                                      |                 |                       |                       | ~2.3                     | 5.24                |                            |
| Japan                                                       | +76.7 Oct                              |                                               | +3.8            | 120                   |                       |                          |                     | 1.75                       |
| China                                                       |                                        | +160.8 2015                                   | +6.7            |                       | 8,07                  |                          | 3,10                | 3.06                       |
| Brtain                                                      | 152.2 Nov                              |                                               |                 | 0.52                  | 0.57                  |                          | 5.31                |                            |
| Canada                                                      |                                        | +28.9 C3                                      | +1.1            | 1.18                  | 1.16                  | 0.7                      |                     | 2.06                       |
| Euro area                                                   | 22.9 da                                |                                               | 0.1             | 0.77                  | 0.83                  |                          | 3.75                | na                         |
| Austria                                                     |                                        | +12.203                                       | +1,4            | 0.77                  | 0.83                  |                          | 3.75                | 4.00                       |
| Belgium                                                     |                                        | +6.8 Sep                                      | +2.2            | 0.77                  | 0.83                  | 0.1                      | 3.80                | 401                        |
| France                                                      |                                        |                                               |                 | 0.77                  | 0.83                  |                          | 3.75                | 4.00                       |
| Germany                                                     | +203.0 Ror                             |                                               |                 | 0.77                  | 0,83                  |                          | 3.75                | 3.97                       |
| Greece                                                      | 41.3 Sep                               |                                               |                 |                       | 0.83                  |                          | 3.75                | 4.26                       |
| Italy                                                       |                                        |                                               | 1.8             | 0.77                  |                       |                          | 3.75                | 4.20                       |
| Netherlands                                                 |                                        |                                               |                 | 0.77                  | 0.83                  | 0.6                      | 3.75                | 3.99                       |
| Spain                                                       |                                        |                                               |                 | 0.77                  | 0.83                  | 0.6                      | 3.75                | 4.02                       |
| Czech Republic                                              |                                        |                                               | 2.7             | 21.4                  | 23.7                  | 4,0                      | 2.56                | 3.75                       |
| Denmark                                                     |                                        |                                               | +2.2            |                       | 6,17                  | 3.0                      | 3.91                | 3.94                       |
| Hungary                                                     | 2.8wov                                 | ~6.9 03                                       |                 | 198                   | 207                   |                          | 8.03                | 7.23                       |
| Nonvay                                                      |                                        | +56.001                                       | +17.6+          | 6.44                  | 6.64                  | 19.3                     | 3.92                | 4,35                       |
| Poland                                                      |                                        |                                               |                 | 3,00                  | 3.13                  |                          | 4.20                | 5.22                       |
| Russia                                                      | +141.2Oct                              | +99.5 03                                      | +7.3            | 26.5                  |                       | 5.9                      | 11.00               | 6.25                       |
| Sweden                                                      |                                        | +26.2 03                                      |                 | 7.06                  | 7.73                  |                          | 3.07                | 3.82                       |
| Switzerland                                                 | +9,/ Mov                               | +105.9 03                                     |                 | 1,25                  | 1.28                  | 1.2                      | 2.13                | 259                        |
| Turkey                                                      |                                        | 34,4 Oct                                      |                 | 1.45                  | 1.34                  | ~2.8                     | 19.71               | 19.79                      |
| Australia                                                   | Mov                                    |                                               |                 | 1.29                  | 1.33                  | 11                       | 6.43                | 5.86                       |
| Kong Hong                                                   | 17.3 Mov                               | +19.2 03                                      | +9.3            |                       | 7.75                  | 11                       | 3.96                | 3.71                       |
| India                                                       |                                        | ~13.7 03                                      |                 | 42.6                  | 44.2                  |                          | 7.12                | 7.67                       |
| Indonesia                                                   |                                        |                                               |                 | 9,080                 | 9,465                 | 0.9                      | 9.57                | 6.205                      |
| Malaysia                                                    | +28,6 Mov                              | +22.2 03                                      |                 | 3.52                  | 3.75                  |                          | 3.73                |                            |
| Pakistan                                                    |                                        | 26.0 03                                       |                 | 61.0                  | 59.8                  |                          | 10.32               | 6.39}                      |
| Singapore                                                   |                                        |                                               | +25.2           | 1.54                  | 1.63                  | 0.3                      | 3.41                | 2,98                       |
| South Korea                                                 |                                        | +6.2 Nov                                      |                 | 938                   | 985                   |                          | 4,87                | 4.91                       |
| Taiwan                                                      | +21.3 De:                              | +26.3 03                                      | +5.0            | 32.7                  | 32.1                  | 2.8                      | 1.82                | 2.08                       |
| Thailand                                                    | +1.3 Mov                               | +2.1 Nov                                      | nil             | 36.0                  | 39.7                  | 1.2                      | 5.25                | 5.04                       |
| Argentina                                                   | +12,0 Mov                              | +6.7 03                                       | +1,6            | 3.08                  | 3.05                  |                          | 10.63               | na                         |
| Brazil                                                      | +46.1 Dez                              | +13.7 Nov                                     | +0.3            | 2.15                  | 2.27                  | 2.2                      | 13.19               |                            |
| Chile                                                       | +22.1 Dec                              | +5.2 05                                       | +2.2            | 542                   | 524                   | 5.8                      | 5.16                | 5.275                      |
| Colombia                                                    | 40.3 Oa                                | 2.3 03                                        |                 | 2,248                 | 2,275                 | 1.5                      | 6,69                |                            |
| Mexico                                                      |                                        |                                               |                 | 11.0                  | 10.6                  |                          |                     | 7.65                       |
| Venezuela                                                   | +36.803                                |                                               | +10.1           | 3,913                 |                       |                          | 10.08               | 6.555                      |
| Egypt                                                       |                                        |                                               | 41,1            | 5.70                  | 2,653                 |                          |                     |                            |
|                                                             | 11.1 02                                | +3.5 02                                       |                 |                       | 5.74                  | ~8.0                     | 9,71                |                            |
| Saudi Arabia                                                |                                        | 490.0 2005                                    | +25.7:          | 3.75                  |                       | 16.8                     |                     | na                         |
| South Africa                                                |                                        |                                               |                 |                       | 1.75                  |                          |                     |                            |
|                                                             |                                        |                                               |                 | 7.33                  | 6.08                  |                          |                     |                            |

## Example Tables III

## Trade, exchange rates and budgets

|               | Trade balance Sbn   | Current-account balance   | Current-account balance   | Current-account balance                          | Current-account balance                          | Exchange rate            | Exchange rate            | Currency units   | Currency units   | Currency units   | Currency units   | Currency units   | Budget                 |
|---------------|---------------------|---------------------------|---------------------------|--------------------------------------------------|--------------------------------------------------|--------------------------|--------------------------|------------------|------------------|------------------|------------------|------------------|------------------------|
|               | [atest 12 months    | Sbn latest 12 mths        | Sbn latest 12 mths        | The Economist % of GDF , forecast 2006 2007 poll | The Economist % of GDF , forecast 2006 2007 poll | trade-weightedi 2000=100 | trade-weightedi 2000=100 | per $            | per $            | per f            | per euto         | per Y100         | balance % of GDP 2006+ |
|               |                     |                           |                           |                                                  |                                                  | Dec 6th                  | year ag0                 | Dec 6th          | yearag0          |                  |                  |                  |                        |
| Australia     | 10.2 Oct            |                           | 03                        | 5.5                                              | 5.1                                              | 119.6                    | 120.0                    | 1.27             | 1.34             | 2.50             | 1.69             | 1.10             | 2.5                    |
| Austra        | 1.2 Sep             | 9,2                       | 02                        | + 1.4                                            |                                                  | 105.85                   | 104.9                    | 0.75             | 0.85             | 1.48             |                  | 0.65             | 1.3                    |
| Belgium       | 16.0 Ser            | 6.5                       | Jun                       | + 1.8                                            | + 2.1                                            | 107.55                   |                          | 0.75             | 0.85             | 1.48             |                  | 0.65             | nil                    |
| Brtain        |                     | 64.4                      | 0?                        | 2.6                                              | 2.7                                              | 103.2                    | 98.8                     | 0.51             | 0.58             |                  | 0.68             | 0.44             | 3.0                    |
| Canada        | 53.7 Sep            | 28.9                      |                           | + 14                                             | + 0.8                                            | 124.9                    | 125.8                    | 1.15             | 1.16             | 2.26             | 1.53             | 1.00             | +0.9                   |
| Denmark       | Sep                 | 7.6                       | SeF                       | 2.3                                              | + 2.2                                            |                          | 105.8                    | 5.60             | 6.35             | 11.0             | 7,46             | 4.87             | 3.4                    |
| France        | 34.9 Sep            | 41.5                      | Sep                       | 1.6                                              | 1.3                                              | 108.45                   | 107.2                    | 0.75             | 0.85             | 1.48             |                  | 0.65             | 2.7                    |
| Germany       | +187.4 Sep          | +107.5                    | Sep                       | + 3.1                                            | + 3,2                                            | 110.25                   | 108.6                    | 0.75             | 0.85             | 1,48             |                  | 0.65             | 2.3                    |
| Italy         | 26.4 Sep            | 39.1                      | Sep                       | 2.3                                              | 1,9                                              | 108.18                   | 106.9                    | 0.75             | 0.85             | 1,48             |                  | 0.65             | 4.8                    |
| Japan         | 78.4 Sep            | +16B.1                    | Sep                       | 3.7                                              | + 3.7                                            | 80.0                     | 80.3                     | 115              | 121              | 226              | 153              |                  | 4,6                    |
| Netherlands   | 38.3 Sep            | 63.2                      | 03                        |                                                  | + 6.3                                            | 108,45                   | 107.3                    | 0.75             | 0.85             | 1.48             |                  | 0.65             | 0,4                    |
| Spain         | 107.4 Sep           | 98.4                      | Aug                       | 8.2                                              | 8.0                                              | 105.95                   | 105.1                    | 0.75             | 0.85             | 1.48             |                  | 0.63             | +1.4                   |
| Sweden        | 19.3 Oct            | 26.2                      | 0?                        | + 6.5                                            | + 6.1                                            | 100.9                    | 95.0                     | 6.80             | 8.02             | 13.4             | 9.06             | 5.92             | +2.9                   |
| Switzerland   | 9.2 Oct             | 55.3                      | 02                        | +13.8                                            | +12.9                                            | 105.7                    | 107.1                    | 1.19             | 1.31             | 2.35             | 1.59             | 1.04             | +0.2                   |
| United States | Sep                 |                           | Q2                        | 6,6                                              | 6.4                                              | 82.0                     | 88.3                     |                  |                  | 1.97             | 1.33             | 0.87             |                        |
| Euro area     | 24.1 Sep            | 35.3                      | Sep                       | 0.3                                              | 0.1                                              | 120.6                    | 114.9                    | 0.75             | 0.85             | 1.48             |                  | 0.65             | 2,1                    |

## Example Tables IV

The Economist of forecasters, December averages (previous month' s, if changed) poll

| Low/high range        | Real GDP , % change average   | Real GDP , % change average   | Real GDP , % change average   | Real GDP , % change average   | Consumer prices % increase   | Consumer prices % increase   | Consumer prices % increase   | Current account % of GDP   | Current account % of GDP   | Current account % of GDP   | Current account % of GDP   |
|-----------------------|-------------------------------|-------------------------------|-------------------------------|-------------------------------|------------------------------|------------------------------|------------------------------|----------------------------|----------------------------|----------------------------|----------------------------|
|                       | 2006                          | 2007                          | 2006                          | 2007                          | 2006                         | 2007                         | 2007                         | 2006                       | 2006                       | 2007                       |                            |
| Australia             | 2.3/2.9                       | 2.3/3.7                       | 2.6 (2.7)                     | 3.0 (3.2)                     | 3.4                          | 2.7                          |                              | -5.5(-5.6)                 |                            | 5.1(-5.2)                  |                            |
| Austria               | 1.9/3.3 1.8/2.6               |                               | 2.8                           | 2.3 (2.1)                     | 1.6 (1.7)                    |                              | 1.6 (1.7)                    |                            | 1,4 (1.1)                  |                            |                            |
| Belgium 2.6/3.0       |                               | 1.8/2.4                       | 2.8 (2.7)                     | 2.0 (1.9)                     | 2.2                          |                              | 1.9 (2,0)                    | 1.8                        |                            | 2.1 {1.9)                  |                            |
| Britain 2.5/2.7       | 1.8/2.8                       |                               | 2.6                           | 2.4                           | 2.3                          |                              | 2.1 (2.2)                    | ~2.6                       |                            | -2.7 (-2.8)                |                            |
| Canada 2.8/3.0        |                               | 2.0/2.9                       | 2.8                           |                               | 2.1 (2.2)                    |                              | 2.0 (2.1)                    | 1.4                        |                            | 0.8 {0.9)                  |                            |
| Denmark 2.8/3.8       |                               | 1.9/3.0                       | 3.3 (3.1)                     |                               | 1.9 (2.0)                    |                              | 1.9 (2.0)                    |                            | (2.0)                      | 2.2 (1.9                   |                            |
| France 2.0/2.3        |                               | 1.6/2.5                       | 2.1 (2.3)                     | 2.0                           | 1.9 (1.8)                    | 1.5                          |                              |                            |                            | -13(-1.2)                  |                            |
| 6ermany 2.2/2.8       |                               | 0.6/2.2                       |                               | 15 (1.4)                      | 1.7                          |                              | 2.2 (2.3)                    | 3.1                        | (3.6)                      | 3.2 (3.7)                  |                            |
| Italy                 | 1.5/1.9                       | 0.9/2.0                       | 1,7                           | 13 (1.2)                      | 2.2                          | 1.9                          |                              |                            | -2.3(-1.8)                 | -19(-1.7)                  |                            |
| Japan 2.7/2.9         | 1.4                           | 3.0                           | 2.8 (2.7)                     | 2.0 (2.1)                     | 0.2 (0.3)                    | 0.5                          |                              | 3.7                        | (3.6)                      | 3.7 (3.6)                  |                            |
| Netherlands 2.5/3.0   | 1.6/2.9                       |                               | 2.7                           | 2.3 (2.2)                     | 1.6                          | 1.7                          |                              |                            | (6.3)                      | 6.3 (5.7)                  |                            |
| Spain 3.3/3.7         |                               | 2.5/3.2                       | 3.5                           | 2.9 (2.8)                     | 3.6 (3.5)                    | 2.8                          |                              |                            | ~8.2(-8.1)                 | ~8.0 (-7.8)                |                            |
| Sweden 4.0/4.7        | 2.6/3.7                       |                               | 4.4                           | 3.2 (3.1)                     | 1.4                          | 1.8                          |                              |                            | 6.5 (6.4)                  | 6.1                        |                            |
| Switzerland 2.,4/3.1  |                               | 1.5/2.6                       | 2.9                           | 2.1                           | 1,2                          |                              | 1.1 (1.2)                    |                            | 13.8(13.5)                 | 12.9                       |                            |
| United States 3.2/3.3 | 1.6/2.9                       |                               | 3.3                           | 2.2 (2.3)                     | 3.3 (3.4)                    |                              | 2.1 (2.3)                    | 46.6                       |                            | ~6.4 (-6.5)                |                            |
| Euro area             | 2.5/2.7                       | 1.5/2.5                       | 2.6                           | 1.9                           | 2.2                          | 2.1                          |                              | ~0.3(-0.4)                 |                            | ~0.1                       |                            |

Sources: ABN AMRO , Deutsche Bank , Economist Intelligence Unit; Goldman Sachs , HSBC Securities , KBC Bank, JPMorgan Chase, Morgan Decision Economics , BNP Paribas, Citigroup, Scotiabank, UBS Stanley ,

## Example Tables V

## The Economist commodity price index

|                         | Nov 2Bth                | Dec Sth'   | % change on one   | one    |
|-------------------------|-------------------------|------------|-------------------|--------|
|                         |                         |            | Month             | year   |
| Dollar index            |                         |            |                   |        |
| Allitems                |                         | 188.3      | + 0.9             | 4      |
| Food                    |                         |            | + 1 9             | 4 25,4 |
| Industrials             |                         |            |                   |        |
| ALL                     | 226,0                   | 232,9      | nil               | + 44.0 |
| Nfat                    | 135.0                   |            | 0.1               | 23     |
| Hetals                  | 275.6                   | 285.2      | + 0.1             | +      |
| Sterling index          |                         |            |                   |        |
| All items               | 144.5                   | 144.9      | 23                | 1 18.9 |
| Eurø index              |                         |            |                   |        |
| All items               | 130.5                   | 130.8      | 3.0               | 19.3   |
| Yen index               |                         |            |                   |        |
| AlL items               | 200.1                   | 201.0      |                   | + 28.2 |
| Gold                    |                         |            |                   |        |
|                         |                         | 643.28     | + 2.8             | + 26.8 |
| West Texas Intermediate | West Texas Intermediate |            |                   |        |
| $ per barrel            | 60,85                   | 62.46      |                   | + 4,2  |

## The Economist commodity-price index 2000-100

|                         |                         |        | % change on   | % change on   |
|-------------------------|-------------------------|--------|---------------|---------------|
|                         | Jan 2nd                 |        | one month     | one year      |
| Dollar index            |                         |        |               |               |
|                         |                         | 168.0  | 9.8           |               |
| Food                    | 157.5                   | 150.1  |               |               |
| Industrials             |                         |        |               |               |
| AlL                     | 225,2                   | 191.1  | ~16.9         | +12.1         |
| Nfa                     | 147.8                   | 147.8  | 45.7          |               |
| Metals                  | 267.5                   |        |               | +15.1         |
| Sterling index          |                         |        |               |               |
| All items               | 143.7                   | 131.2  | 8.6           | 43.2          |
| Euro index              |                         |        |               |               |
| All items               | 130.2                   | 119.4  |               | 45.3          |
| Gold                    |                         |        |               |               |
|                         | 640.70                  | 609.10 |               | +12.4         |
| West Texas Intermediate | West Texas Intermediate |        |               |               |
| 5 per barrel            | 60.77                   |        |               | -12.2         |

Prcsisional
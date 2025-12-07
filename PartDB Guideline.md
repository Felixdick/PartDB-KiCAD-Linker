# PartDB Guideline

# **Living Documents - Not Released!!!**

# **Component Library Architecture**

## **1\. Philosophy and Goals:**

- **Automated BOM Analysis:** Cost estimation, availability checks, and mass calculation.
- **Compliance Tracking:** Instant generation of RoHS/REACH/UL reports.
- **Design Validation:** Automated checks for power ratings and thermal constraints.
- **Reliability Prediction:** MTBF (Mean Time Between Failures) calculations based on stored FIT rates.

## **2\. PartDB Native Fields (Standard Tabs)**

#### **A. Tab: Common**

- **Name:** **MUST be the MPN (Manufacturer Part Number).**
- **Description:** Strict technical description.
    - _Format passives:_ `[Category] [Values] [Tolerance] [Package]` (e.g., ` 10k 1/10W 1% 0603`).
    - _Format actives:_ `[Category] [Features] [Package]` (e.g., `OpAmp Dual Channel Rail to Rail`).
- **Category:** Select from the tree structure (defined in Section 4).
- **Tags:** Not mandatory
- **Minimum Stock:** N/A
- **Footprint:** The physical land pattern name.
    - _Format:_ `[Manufacturer]_[Drawing Number]_[Footprint Name]` (e.g., `TI_DGK0008A_VSSOP8`).

#### **B. Tab: Manufacturer**

- **Manufacturer:** The actual silicon/part producer (e.g., `Texas Instruments`).
- **Manufacturer Part Number:** Manufacturer Part Number.
- **Link to Product Page:** URL to the specific component page on the MFG website.
- **Manufacturing Status:**
    - _PartDB Mapping (_**_Must not be NRND or Obsolete when creating part)_**_:_
    - _Managed via API/Automatic Updates_
        - `Active` = Preferred for new designs.
        - `NRND` = Not Recommended for New Designs.
        - `Obsolete` = Do not use.
        - `Preliminary` = Risk assessment required.

#### **C. Tab: Advanced**

- **Mass:** Component weight in **grams (g)**.
- **Internal Part Number:** N/A
- **Measuring Unit:** N/A

#### **D. Tab: Purchase Information**

- **Supplier:** Primary Distributor (e.g., DigiKey, Mouser).
- **Supplier PN:** The distributor's SKU (used for API pricing fetch).
- **Link to Offer:** Direct URL to the distributor's product page.
- **Price:** _Managed via API/Automatic Updates_ (Do not manually populate).

### **3\. PartDB Parameters Tab (Custom Globals)**

#### **A. Reliability & Ratings (Mandatory)**

- `FIT_Rate`**:**
- `Op_Temp_Min`**:** (Celsius) [°C]
- `Op_Temp_Max`**:** (Celsius) [°C]
- `RoHS_Compliant`**:**
- `REACH_Compliant`**:**
- `UL_Rating`**:**
- `Datasheet_Link`**:**

### **4\. Category Tree & Specific Parameters**

Structure PartDB categories exactly as follows. Parameters listed are _in addition_ to the Globals above. Subcategories shall be extended if needed.

#### **1.0 Resistors**

- **Shared Parameters:** `Resistance_Ohms`, `Tolerance`, `Power_W`, `Voltage_Rated_V`
    - **1.1 Thick Film**
    - **1.2 Thin Film**: -> Add `TCR_ppm`
    - **1.3 Current Sense**: -> Add `TCR_ppm`, `Pulse_Rating_J`
    - **1.4 Arrays/Networks**: -> Add `Element_Count`
    - **1.5 Potentiometers**: -> Add `Adjustment_Type`, `Turns`

#### **2.0 Capacitors**

- **Shared Parameters:** `Capacitance_F`, `Voltage_Rated_V`, `Tolerance`
    - **2.1 MLCC**: -> Add `Dielectric`, `DC_Bias_Loss` (at 1/2 rated voltage)
    - **2.2 Elko**: -> Add `ESR_Ohms`, `Ripple_Current_mA`, `Lifetime_Hours`
    - **2.3 Tantalum/Polymer**: -> Add `ESR_Ohms`, `Case_Code`
    - **2.4 Film**: -> Add `Dielectric_Material`, `dv/dt`
    - **2.5 Supercapacitors**: -> Add `ESR_Ohms`

#### **3.0 Inductors & Magnetics**

- **Shared Parameters:** `Inductance_H`, `DCR_Ohms`, `I_Sat_A`, `I_Rated_A`, `Tolerance`
    - **3.1 Power Inductors**: -> Add `Shielding`
    - **3.2 RF Inductors**: -> Add `Q_Factor`, `SRF_MHz`
    - **3.3 Ferrite Beads**: -> Add `Impedance_100MHz_Ohms`
    - **3.4 Common Mode Chokes**: -> Add `Impedance_Common_Mode`, `Leakage_Inductance`
    - **3.5 Transformers**: -> Add `Turns_Ratio`, `Isolation_Voltage_V`

#### **4.0 Discrete Semiconductors**

- **Shared Parameters:** `Theta_JC`, `Tj_Max`
    - **4.1 Diodes**
        - **4.1.1 Rectifier/Switching**: `V_Reverse_V`, `I_Forward_A`, `V_Forward_V`, `Trr_ns`
        - **4.1.2 Zener**: `V_Zener_V`, `Power_W`, `Impedance_Zzt`
        - **4.1.3 Schottky**: `V_Reverse_V`, `I_Forward_A`, `V_Forward_V`
        - **4.1.4 TVS**: `V_StandOff_V`, `V_Clamp_V`, `P_Peak_Pulse_W`, `Uni_Bi_Directional`
        - **4.1.5 LEDs**: `Color`, `Wavelength_nm`, `Luminous_Intensity_mcd`, `I_Test_mA`
    - **4.2 Transistors**
        - **4.2.1 FETs**: `Ch_Type`, `SC_Material`, `V_DSS_V`, `I_D_A`, `R_DS_on_Ohms`, `V_GS_th_V`, `Qg_nC`, `Theta_JA`
        - **4.2.2 BJTs**: `Type`, `V_CE_V`, `I_C_A`, `hFE_Gain`, `fT_MHz`
        - **4.2.3 IGBTs**: `V_CES_V`, `I_C_A`, `V_CE_sat_V`, `Switching_Energy_mJ`

#### **5.0 Integrated Circuits (ICs)**

- **Shared Parameters:** `Supply_V_Min`, `Supply_V_Max`, `I_Quiescent_uA`, `Package_Type`, `Theta_JC`, `Tj_Max`
    - **5.1 Power Management**
        - **5.1.1 Linear / LDO**: `V_Out_V`, `I_Out_Max_A`, `Dropout_V`, `PSRR_dB`
        - **5.1.2 Switching DC/DC**: `Topology`, `V_Out_Range`, `I_Out_Max_A`, `Freq_Switch_kHz`
        - **5.1.3 PMIC**: `Output_Count`, `Interface`
        - **5.1.4 BMS / Battery**: `Cell_Count`, `Protection_Features`
        - **5.1.5 Voltage Reference**: `V_Ref_V`, `Accuracy`, `Drift_ppm`
    - **5.2 Microcontrollers & Processing**
        - **5.2.1 MCU**: `Core`, `Speed_MHz`, `Flash_Size_kB`, `RAM_Size_kB`, `GPIO_Count`
        - **5.2.2 FPGA**: `Logic_Cells`, `Block_RAM_bits`, `DSP_Slices`
    - **5.3 Analog & Mixed Signal**
        - **5.3.1 OpAmps**: `Bandwidth_MHz`, `Slew_Rate_V/us`, `V_Offset_uV`, `Rail_to_Rail`
        - **5.3.2 Comparators**: `Prop_Delay_ns`, `Hysteresis_mV`
        - **5.3.3 ADC**: `ADC_Type`, `Resolution_Bits`, `Sample_Rate_kSPS`, `Channels`, `Interface`
        - **5.3.4 DAC**: `DAC_Type`, `Resolution_Bits`, `Channels`, `Settling_Time_us`
    - **5.4 Logic**
        - **5.4.1 Gates/Inverters**: `Logic_Level_V`, `Prop_Delay_ns`
        - **5.4.2 Level Shifters**: `Direction`, `Data_Rate_Mbps`
        - **5.4.3 Buffers/Drivers**: `Output_Drive_mA`, `Channels`, `Driver_Type`
    - **5.5 Interface**
        - **5.5.1 Transceivers**: `Protocol`, `Data_Rate`, `Isolation_V`
        - **5.5.2 Switches/Mux**: `Configuration`, `On_Resistance_Ohms`
    - **5.6 Memory**
        - **5.6.1 Flash**: `Size_Mbit`, `Interface`
        - **5.6.2 EEPROM**: `Size_kbit`, `Interface`
        - **5.6.3 RAM**: `Type`, `Size_Mbit`
    - **5.7 Sensors**
        - **5.7.1 Environmental**: `Measurand`, `Range`, `Accuracy`, `Response_Time`
        - **5.7.2 Motion / IMU**: `Type`, `Axes`, `Sensitivity_LSB_g`, `Noise_Density`
        - **5.7.3 Optical**: `Type`, `Wavelength_nm`, `Range_mm`
        - **5.7.4 Magnetic / Hall**: `Type`, `Operating_Point_mT`, `Output`
        - **5.7.5 Audio (MEMS Mic)**: `SNR_dB`, `Sensitivity_dB`
        - **5.7.6 Image Sensors**: `Resolution_MP`, `Optical_Format`, `Shutter_Type`
        - **5.7.7 Current Sensors**: `Sensing_Method`, `Range_A`, `Sensitivity_mV/A`, `Isolation_V`, `Bandwidth_kHz`

#### **6.0 Connectors**

- **Shared Parameters:** `Pitch_mm`, `Pin_Count`, `Mounting`, `Current_Rating_A`, `Gender`, `Orientation`, `Number_Rows`, `Pin_Annotation`
    - **6.1 Board-to-Board**: -> Add `Series`
    - **6.2 Wire-to-Board**: -> Add `Series`
    - **6.3 I/O Connectors**: -> Add `Type`, `Standard_Version`
    - **6.4 Terminal Blocks**: -> Add `Wire_Gauge_AWG`, `Termination`

#### **7.0 Mechanical**

- **Shared Parameters:** `Material`, `Finish`, `Thread_Size`, `Length_mm`

#include "./ooasp.lp".

% domain specific constraints below

% The CPU and motherboard must be compatible (i.e., the motherboard supports the CPU type).
%
% The motherboard should be compatible with the selected CPU (for example, a motherboard
% supporting Intel CPUs cannot support AMD CPUs, etc.).
:- ooasp_associated(I, "Motherboard_cpu", Motherboard, CPU),
   ooasp_attribute_value(I, "cpu_type", CPU, CPUTyp),
   ooasp_attribute_value(I, "supported_cpu_type", Motherboard, SupportedType),
   CPUTyp != SupportedType.

% A motherboard can only support a specific amount of RAM (e.g., the motherboard supports 
% only a maximum of 64GB of RAM).
%
% If the motherboard is selected, ensure that the total size of the associated RAM modules 
% does not exceed the supported RAM size.
:- ooasp_associated(I, "Motherboard_ram", Motherboard, RAM),
   ooasp_attribute_value(I, "ram_size", RAM, Size),
   ooasp_attribute_value(I, "max_ram_size", Motherboard, MaxSize),
   Size > MaxSize.

% The computer cannot have more than 2 storage devices.
%
% If a storage device is selected, ensure that the total number of associated storage devices
% for the computer does not exceed the allowed maximum (e.g., 2).
:- ooasp_associated(I, "Motherboard_storage", Motherboard, Storage),
   Cnt = #count { Device : ooasp_associated(I, "Motherboard_storage", Motherboard, Device) },
   Cnt > 2.

% Ensure that the storage type for a computer is either "SSD" or "HDD" (it cannot be both).
%
% If a storage device is associated with the computer, ensure that its type is either "SSD" or "HDD".
:- ooasp_attribute_value(I, "storage_type", Storage, Type),
   Type != "SSD", Type != "HDD".

% If the CPU selected is a high-performance CPU, ensure that the motherboard has a compatible chipset.
%
% If a CPU is selected as high-performance, the associated motherboard must have the necessary 
% chipset to support the CPU.
:- ooasp_attribute_value(I, "cpu_performance", CPU, "High_Performance"),
   ooasp_associated(I, "Motherboard_cpu", Motherboard, CPU),
   ooasp_attribute_value(I, "chipset", Motherboard, Chipset),
   Chipset != "High_Performance_Compatible".

% RAM size must be an integer and the value must be within the limits (e.g., 4GB, 8GB, 16GB, etc.).
%
% Ensure that the RAM size selected is within the supported values for the system.
:- ooasp_attribute_value(I, "RAM", "size", Size),
   Size < 4; Size > 128.

% Powersupply wattage must be an integer and the value must be within the limits between 300 and 2000 watts.
%
% Ensure that the Powersupply wattage selected is within the supported values for the system.
:- ooasp_attribute_value(I, "Powersupply", "wattage", wattage),
   wattage < 300; wattage > 2000.
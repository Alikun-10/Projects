#include "../computer-config-model.lp".

% Instance of motherboard_6
ooasp_instance("v1", "Motherboard_6", "Motherboard").
ooasp_instance("v1", "Motherboard_6", "ComputerComponent").
ooasp_assoc("v1", "Motherboard_cpu", "Motherboard_6", 1, 1, "CPU_6", 1, 1).
ooasp_assoc("v1", "Motherboard_ram", "Motherboard_6", 1, 4, "RAM_6", 1, 4).
ooasp_assoc("v1", "Motherboard_storage", "Motherboard_6", 1, 2, "Storage_6", 1, 2).
ooasp_assoc("v1", "Motherboard_graphics_card", "Motherboard_6", 1, 1, "GraphicsCard_6", 1, 1).
ooasp_assoc("v1", "Motherboard_power_supply", "Motherboard_6", 1, 1, "PowerSupply_6", 1, 1).

% CPU instance
ooasp_instance("v1", "CPU_6", "CPU").
ooasp_attribute("v1", "CPU_6", "core_count", 4).

% RAM instance
ooasp_instance("v1", "RAM_6", "RAM").
ooasp_attribute("v1", "RAM_6", "size", 16).

% Storage instance
ooasp_instance("v1", "Storage_6", "Storage").
ooasp_attribute("v1", "Storage_6", "storage_type", "HDD").
ooasp_attribute("v1", "Storage_6", "size", 750).

% GraphicsCard instance
ooasp_instance("v1", "GraphicsCard_6", "GraphicsCard").
ooasp_attribute("v1", "GraphicsCard_6", "vram_size", 6).

% PowerSupply instance
ooasp_instance("v1", "PowerSupply_6", "PowerSupply").
ooasp_attribute("v1", "PowerSupply_6", "wattage", 600).

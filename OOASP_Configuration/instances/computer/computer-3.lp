#include "../computer-config-model.lp".

% Instance of motherboard_3
ooasp_instance("v1", "Motherboard_3", "Motherboard").
ooasp_instance("v1", "Motherboard_3", "ComputerComponent").
ooasp_assoc("v1", "Motherboard_cpu", "Motherboard_3", 1, 1, "CPU_3", 1, 1).
ooasp_assoc("v1", "Motherboard_ram", "Motherboard_3", 1, 4, "RAM_3", 1, 4).
ooasp_assoc("v1", "Motherboard_storage", "Motherboard_3", 1, 2, "Storage_3", 1, 2).
ooasp_assoc("v1", "Motherboard_graphics_card", "Motherboard_3", 1, 1, "GraphicsCard_3", 1, 1).
ooasp_assoc("v1", "Motherboard_power_supply", "Motherboard_3", 1, 1, "PowerSupply_3", 1, 1).

% CPU instance
ooasp_instance("v1", "CPU_3", "CPU").
ooasp_attribute("v1", "CPU_3", "core_count", 4).

% RAM instance
ooasp_instance("v1", "RAM_3", "RAM").
ooasp_attribute("v1", "RAM_3", "size", 8).

% Storage instance
ooasp_instance("v1", "Storage_3", "Storage").
ooasp_attribute("v1", "Storage_3", "storage_type", "SSD").
ooasp_attribute("v1", "Storage_3", "size", 250).

% GraphicsCard instance
ooasp_instance("v1", "GraphicsCard_3", "GraphicsCard").
ooasp_attribute("v1", "GraphicsCard_3", "vram_size", 4).

% PowerSupply instance
ooasp_instance("v1", "PowerSupply_3", "PowerSupply").
ooasp_attribute("v1", "PowerSupply_3", "wattage", 500).

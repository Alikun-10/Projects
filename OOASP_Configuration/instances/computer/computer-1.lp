#include "../computer-config-model.lp".

% Instance of motherboard_1
ooasp_instance("v1", "Motherboard_1", "Motherboard").
ooasp_instance("v1", "Motherboard_1", "ComputerComponent").
ooasp_assoc("v1", "Motherboard_cpu", "Motherboard_1", 1, 1, "CPU_1", 1, 1).
ooasp_assoc("v1", "Motherboard_ram", "Motherboard_1", 1, 4, "RAM_1", 1, 4).
ooasp_assoc("v1", "Motherboard_storage", "Motherboard_1", 1, 2, "Storage_1", 1, 2).
ooasp_assoc("v1", "Motherboard_graphics_card", "Motherboard_1", 1, 1, "GraphicsCard_1", 1, 1).
ooasp_assoc("v1", "Motherboard_power_supply", "Motherboard_1", 1, 1, "PowerSupply_1", 1, 1).

% CPU instance
ooasp_instance("v1", "CPU_1", "CPU").
ooasp_attribute("v1", "CPU_1", "core_count", 8).

% RAM instance
ooasp_instance("v1", "RAM_1", "RAM").
ooasp_attribute("v1", "RAM_1", "size", 16).

% Storage instance
ooasp_instance("v1", "Storage_1", "Storage").
ooasp_attribute("v1", "Storage_1", "storage_type", "SSD").
ooasp_attribute("v1", "Storage_1", "size", 500).

% GraphicsCard instance
ooasp_instance("v1", "GraphicsCard_1", "GraphicsCard").
ooasp_attribute("v1", "GraphicsCard_1", "vram_size", 8).

% PowerSupply instance
ooasp_instance("v1", "PowerSupply_1", "PowerSupply").
ooasp_attribute("v1", "PowerSupply_1", "wattage", 750).

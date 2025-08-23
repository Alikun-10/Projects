#include "../computer-config-model.lp".

% Instance of motherboard_2
ooasp_instance("v1", "Motherboard_2", "Motherboard").
ooasp_instance("v1", "Motherboard_2", "ComputerComponent").
ooasp_assoc("v1", "Motherboard_cpu", "Motherboard_2", 1, 1, "CPU_2", 1, 1).
ooasp_assoc("v1", "Motherboard_ram", "Motherboard_2", 1, 4, "RAM_2", 1, 4).
ooasp_assoc("v1", "Motherboard_storage", "Motherboard_2", 1, 2, "Storage_2", 1, 2).
ooasp_assoc("v1", "Motherboard_graphics_card", "Motherboard_2", 1, 1, "GraphicsCard_2", 1, 1).
ooasp_assoc("v1", "Motherboard_power_supply", "Motherboard_2", 1, 1, "PowerSupply_2", 1, 1).

% CPU instance
ooasp_instance("v1", "CPU_2", "CPU").
ooasp_attribute("v1", "CPU_2", "core_count", 16).

% RAM instance
ooasp_instance("v1", "RAM_2", "RAM").
ooasp_attribute("v1", "RAM_2", "size", 32).

% Storage instance
ooasp_instance("v1", "Storage_2", "Storage").
ooasp_attribute("v1", "Storage_2", "storage_type", "HDD").
ooasp_attribute("v1", "Storage_2", "size", 1000).

% GraphicsCard instance
ooasp_instance("v1", "GraphicsCard_2", "GraphicsCard").
ooasp_attribute("v1", "GraphicsCard_2", "vram_size", 12).

% PowerSupply instance
ooasp_instance("v1", "PowerSupply_2", "PowerSupply").
ooasp_attribute("v1", "PowerSupply_2", "wattage", 1000).

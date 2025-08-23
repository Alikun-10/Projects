#include "../computer-config-model.lp".

% Instance of motherboard_7
ooasp_instance("v1", "Motherboard_7", "Motherboard").
ooasp_instance("v1", "Motherboard_7", "ComputerComponent").
ooasp_assoc("v1", "Motherboard_cpu", "Motherboard_7", 1, 1, "CPU_7", 1, 1).
ooasp_assoc("v1", "Motherboard_ram", "Motherboard_7", 1, 4, "RAM_7", 1, 4).
ooasp_assoc("v1", "Motherboard_storage", "Motherboard_7", 1, 2, "Storage_7", 1, 2).
ooasp_assoc("v1", "Motherboard_graphics_card", "Motherboard_7", 1, 1, "GraphicsCard_7", 1, 1).
ooasp_assoc("v1", "Motherboard_power_supply", "Motherboard_7", 1, 1, "PowerSupply_7", 1, 1).

% CPU instance
ooasp_instance("v1", "CPU_7", "CPU").
ooasp_attribute("v1", "CPU_7", "core_count", 12).

% RAM instance
ooasp_instance("v1", "RAM_7", "RAM").
ooasp_attribute("v1", "RAM_7", "size", 32).

% Storage instance
ooasp_instance("v1", "Storage_7", "Storage").
ooasp_attribute("v1", "Storage_7", "storage_type", "SSD").
ooasp_attribute("v1", "Storage_7", "size", 512).

% GraphicsCard instance
ooasp_instance("v1", "GraphicsCard_7", "GraphicsCard").
ooasp_attribute("v1", "GraphicsCard_7", "vram_size", 8).

% PowerSupply instance
ooasp_instance("v1", "PowerSupply_7", "PowerSupply").
ooasp_attribute("v1", "PowerSupply_7", "wattage", 800).

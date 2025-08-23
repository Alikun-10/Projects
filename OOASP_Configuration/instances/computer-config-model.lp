% classes
ooasp_class("v1","Motherboard").
ooasp_class("v1","CPU").
ooasp_class("v1","RAM").
ooasp_class("v1","Storage").
ooasp_class("v1","GraphicsCard").
ooasp_class("v1","PowerSupply").

% class inheritance
ooasp_subclass("v1","Motherboard","ComputerComponent").
ooasp_subclass("v1","CPU","ComputerComponent").
ooasp_subclass("v1","RAM","ComputerComponent").
ooasp_subclass("v1","Storage","ComputerComponent").
ooasp_subclass("v1","GraphicsCard","ComputerComponent").
ooasp_subclass("v1","PowerSupply","ComputerComponent").

% attributes and associations
% class Motherboard
ooasp_assoc("v1","Motherboard_cpu","Motherboard",1,1,"CPU",1,1).
ooasp_assoc("v1","Motherboard_ram","Motherboard",1,4,"RAM",1,4).
ooasp_assoc("v1","Motherboard_storage","Motherboard",1,2,"Storage",1,2).
ooasp_assoc("v1","Motherboard_graphics_card","Motherboard",1,1,"GraphicsCard",1,1).
ooasp_assoc("v1","Motherboard_power_supply","Motherboard",1,1,"PowerSupply",1,1).

% class CPU
ooasp_attribute("v1", "CPU", "core_count", "integer").
ooasp_attribute_minInclusive("v1", "CPU", "core_count", 1).
ooasp_attribute_maxInclusive("v1", "CPU", "core_count", 64).

% class RAM
ooasp_attribute("v1", "RAM", "size", "integer").
ooasp_attribute_minInclusive("v1", "RAM", "size", 4).
ooasp_attribute_maxInclusive("v1", "RAM", "size", 128).

% class Storage
ooasp_attribute("v1", "Storage", "storage_type", "string").
ooasp_attribute_enum("v1", "Storage", "storage_type", "SSD").
ooasp_attribute_enum("v1", "Storage", "storage_type", "HDD").
ooasp_attribute("v1", "Storage", "size", "integer").
ooasp_attribute_minInclusive("v1", "Storage", "size", 120).
ooasp_attribute_maxInclusive("v1", "Storage", "size", 2000).

% class GraphicsCard
ooasp_attribute("v1", "GraphicsCard", "vram_size", "integer").
ooasp_attribute_minInclusive("v1", "GraphicsCard", "vram_size", 2).
ooasp_attribute_maxInclusive("v1", "GraphicsCard", "vram_size", 24).

% class PowerSupply
ooasp_attribute("v1", "PowerSupply", "wattage", "integer").
ooasp_attribute_minInclusive("v1", "PowerSupply", "wattage", 300).
ooasp_attribute_maxInclusive("v1", "PowerSupply", "wattage", 2000).

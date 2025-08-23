% bike example kb "v1"
% classes
ooasp_class("v1","Frame").
ooasp_class("v1","Wheel").
ooasp_class("v1","Saddle"). 
ooasp_class("v1","WheelFront").
ooasp_class("v1","WheelBack"). 


% class inheritance
ooasp_subclass("v1","Frame","BikeComponent").
ooasp_subclass("v1","Wheel","BikeComponent").
ooasp_subclass("v1","Saddle","BikeComponent").
ooasp_subclass("v1","WheelFront","Wheel").
ooasp_subclass("v1","WheelBack","Wheel").


% attributes and associations
% class Frame
ooasp_assoc("v1","Frame_wheel_front","Frame",1,1,"WheelFront",1,1).
ooasp_assoc("v1","Frame_wheel_back","Frame",1,1,"WheelBack",1,1).
ooasp_assoc("v1","Frame_saddle","Frame",1,1,"Saddle",1,1).
ooasp_attribute("v1", "Frame", "child_model", "boolean").
ooasp_attribute("v1", "Frame", "gears", "string").
ooasp_attribute("v1","Wheel","wheel_size","integer").
ooasp_attribute_minInclusive("v1","Wheel","wheel_size",14).
ooasp_attribute_maxInclusive("v1","Wheel","wheel_size",20).
ooasp_attribute_enum("v1", "Frame", "gears", "Hub").
ooasp_attribute_enum("v1", "Frame", "gears", "Derailleur").


#include "./ooasp.lp".

% domain specific constraints below

% The front and back wheels associated with a frame must be of the
% same size.
%
% Your domain-specific constraint goes here...
:- ooasp_associated(I, "Frame_wheel_front", Frame, FrontWheel),
   ooasp_associated(I, "Frame_wheel_back", Frame, BackWheel),
   ooasp_attribute_value(I, "wheel_size", FrontWheel, Size1),
   ooasp_attribute_value(I, "wheel_size", BackWheel, Size2),
   Size1 != Size2.

% If child_model is selected for a frame, both wheels associated with
% said frame cannot be larger than 16.
%
% Your domain-specific constraint goes here...
:- ooasp_attribute_value(I, "child_model", Frame, "TRUE"),
   ooasp_associated(I, "Frame_wheel_front", Frame, FrontWheel),
   ooasp_attribute_value(I, "wheel_size", FrontWheel, Size),
   Size > 16.

:- ooasp_attribute_value(I, "child_model", Frame, "TRUE"),
   ooasp_associated(I, "Frame_wheel_back", Frame, BackWheel),
   ooasp_attribute_value(I, "wheel_size", BackWheel, Size),
   Size > 16.
		
% If child_model is selected for a frame, the selected gears for said
% frame must be derailleur.
%
% Your domain-specific constraint goes here...
:- ooasp_attribute_value(I, "child_model", Frame, "TRUE"),
   ooasp_attribute_value(I, "gears", Frame, GearType),
   GearType != "Derailleur".

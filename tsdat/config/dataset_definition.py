import act
import datetime
import warnings
import numpy as np
import xarray as xr
from typing import Dict, List, Tuple
from .keys import Keys
from .attribute_defintion import AttributeDefinition
from .dimension_definition import DimensionDefinition
from .variable_definition import VariableDefinition
from tsdat.exceptions import DefinitionError


class DatasetDefinition:
    def __init__(self, dictionary: Dict, pipeline_type: str):
        self.attrs = self._parse_attributes(dictionary, pipeline_type)
        self.attrs = self._add_autogenerated_attributes(self.attrs, dictionary.get(Keys.ATTRIBUTES))
        self.dims = self._parse_dimensions(dictionary)
        self.vars = self._parse_variables(dictionary, self.dims)
        self.coords, self.vars = self._parse_coordinates(self.vars)
        self._validate_dataset_definition()

    def _parse_attributes(self, dictionary: Dict, pipeline_type: str) -> Dict[str, AttributeDefinition]:
        attributes: Dict[str, AttributeDefinition] = {}
        for attr_name, attr_value in dictionary.get(Keys.ATTRIBUTES, {}).items():
            attributes[attr_name] = AttributeDefinition(attr_name, attr_value)
        attributes["data_level"] = self._parse_data_level(pipeline_type)
        return attributes
    
    def _parse_data_level(self, pipeline_type: str) -> AttributeDefinition:
        types = {"Ingest": "b1", "VAP": "c1"}
        data_level = types.get(pipeline_type, None)
        if not data_level:
            raise DefinitionError(f"Pipeline type: {pipeline_type} is not a valid pipeline type.")
        return AttributeDefinition("data_level", data_level)

    def _add_autogenerated_attributes(self, attrs: Dict[str, AttributeDefinition], dictionary: Dict) -> Dict[str, AttributeDefinition]:
        """-------------------------------------------------------------------
        Creates handles for several required attributes that must be set 
        before runtime.

        Args:
            dictionary (Dict): The dictionary containing global attributes.
        -------------------------------------------------------------------"""
        # Generate attributes that can be generated now -- history and datastream
        # Create handles for each and add to attrs dictionary
        attrs["history"]    = self._generate_history(dictionary)
        attrs["datastream"] = self._generate_datastream()
        
        self.history        = attrs["history"].value
        self.datastream     = attrs["datastream"].value

        return attrs

    def _parse_dimensions(self, dictionary: Dict) -> Dict[str, DimensionDefinition]:
        dimensions: Dict[str, DimensionDefinition] = {}
        for dim_name, dim_dict in dictionary[Keys.DIMENSIONS].items():
            dimensions[dim_name] = DimensionDefinition(dim_name, dim_dict)
        return dimensions

    def _parse_variables(self, dictionary: Dict, available_dimensions: Dict[str, DimensionDefinition]) -> Dict[str, VariableDefinition]:
        variables: Dict[str, VariableDefinition] = {}
        for var_name, var_dict in dictionary[Keys.VARIABLES].items():
            variables[var_name] = VariableDefinition(var_name, var_dict, available_dimensions)
        return variables
    
    def _parse_coordinates(self, vars: Dict[str, VariableDefinition]) -> Tuple[Dict[str, VariableDefinition], Dict[str, VariableDefinition]]:
        """-------------------------------------------------------------------
        Determines which variables are coordinate variables and moves those 
        variables from self.vars to self.coords. Coordinate variables are 
        variables that are dimensioned by themself. I.e. `var.name == 
        var.dim.name` is a true statement for coordinate variables.

        Args:
            vars (Dict[str, VariableDefinition]):   The dictionary of 
                                                    variables to check.
            dims (Dict[str, DimensionDefinition]):  The dictionary of 
                                                    dimensions in the dataset.
        -------------------------------------------------------------------"""
        coords = {name: var for name, var in vars.items() if var.is_coordinate()}
        vars = {name: var for name, var in vars.items() if not var.is_coordinate()}
        return coords, vars

    def _generate_datastream(self) -> AttributeDefinition:
        loc_id      = self.attrs.get("location_id").value
        instr_id    = self.attrs.get("instrument_id").value
        qualifier   = self.attrs.get("qualifier", AttributeDefinition(None, "")).value
        temporal    = self.attrs.get("temporal", AttributeDefinition(None, "")).value
        data_level  = self.attrs.get("data_level").value
        datastream_name = f"{loc_id}.{instr_id}{qualifier}{temporal}.{data_level}"
        return AttributeDefinition("datastream", datastream_name)

    def _generate_history(self, dictionary: Dict) -> AttributeDefinition:
        # Should generate a string like: "Ran by user <USER> on machine <MACHINE> at <DATE>"
        # TODO: Add user
        # TODO: Add machine, if possible
        date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return AttributeDefinition("history", f"Ran at {date}")
    
    def _validate_dataset_definition(self):
        """-------------------------------------------------------------------
        Performs sanity checks on the dataset definition after it has been 
        parsed from the yaml file.

        Raises:
            DefinitionError: Raises a DefinitionError if a sanity check fails.
        -------------------------------------------------------------------"""
        # sanity check: time dimension and coordinate variable are present
        self._error_check_time_definition()
        
        # sanity check: raise warning if no coordinate variable for a dimension
        self._warn_check_dimension_definitions()

        # sanity check: coordinate variables are dimensioned by themselves
        self._error_check_coordinate_definitions()

        # check that all required global attributes are present
        self._error_check_required_global_attrs()

        # sanity check: components that make up datastream name conform with 
        #               standards
        self._error_check_datastream_name_components()

        # TODO: Check Variable attributes -- _FillValue defined only on non-coordinate variables,
        # warning if no long_name provided, units recognized by our units library, etc


    def _error_check_time_definition(self):
        # Ensure that time is in the dataset definition as a dimension and a coordinate variable
        assert "time" in self.dims,     DefinitionError("'time' must be defined as a dimension.")
        assert "time" in self.coords,   DefinitionError("'time' must be defined as a coordinate variable.")

    def _warn_check_dimension_definitions(self):
        # Check that all dims have a coordinate variable defined
        for dim in self.dims:
            if dim not in self.coords:
                warnings.warn(f"Dimension {dim} does not have an associated coordinate variable")

    def _error_check_coordinate_definitions(self):
        for coord_name, coord in self.coords.items():
            assert len(coord.dims)==1,      DefinitionError(f"Coordinate variable '{coord_name}' must have exactly one dimension.")
            assert coord_name in self.dims, DefinitionError(f"'{coord_name}' must be dimensioned by dimensioned by itself")

    def _error_check_required_global_attrs(self):
        required_attrs: List[str] = [
            "title",
            "description",
            "conventions",
            "history",
            "code_url",
            "location_id",
            "instrument_id",
            "datastream",
            "data_level"
        ]
        for attr_name in required_attrs:
            attr_value = self.attrs.get(attr_name, AttributeDefinition(None, None)).value
            assert attr_value, DefinitionError(f"'{attr_name}' is a required global attribute")

    def _error_check_datastream_name_components(self):
        datastream_components = [
            "location_id", 
            "instrument_id", 
            "qualifier", 
            "temporal", 
            "data_level"
        ]
        for attr_name in datastream_components:
            attr_value = self.attrs.get(attr_name, AttributeDefinition(None, None)).value
            if attr_value:
                # I think we only require that it has no .'s -- any other character is allowed?
                assert "." not in attr_value, DefinitionError(f"'.' is not an allowed character for {attr_name}")
        
        # Data level must follow specific format
        data_level = self.attrs.get("data_level").value
        assert isinstance(data_level, str), DefinitionError("Data level must be a string.")
        assert len(data_level) == 2,        DefinitionError("Data level must consist of two characters.")
        if data_level != "00":
            assert data_level[0].isalpha(),     DefinitionError("Data level first character must be a letter.")
            assert data_level[1].isnumeric(),   DefinitionError("Data level second character must be a number.")
        else:
            warnings.warn("Data level chosen is 00, which is not recommended.")

    def add_input_files_attr(self, input_files: List[str]):
        if input_files is None:
            return
        _input_files = ", ".join(input_files)
        self.attrs["input_files"] = AttributeDefinition("input_files", _input_files)
    
    def get_attr(self, attribute_name):
        attr = self.attrs.get(attribute_name, None)
        if attr:
            return attr.value
        return None

    def get_variable_names(self) -> List[str]:
        return list(self.vars.keys())

    def get_variable(self, variable_name: str) -> VariableDefinition:
        variable = self.vars.get(variable_name, None)
        if variable is None:
            variable = self.coords.get(variable_name, None)
        return variable
    
    def get_coordinates(self, variable: VariableDefinition) -> List[VariableDefinition]:
        """-------------------------------------------------------------------
        Returns the coordinate VariableDefinition(s) that dimension the 
        provided variable.

        Args:
            variable (VariableDefinition):  The VariableDefinition whose 
                                            coordinate variables should be 
                                            retrieved.

        Returns:
            List[VariableDefinition]:   A list of VariableDefinition 
                                        coordinate variables that dimension
                                        the given VariableDefinition.
        -------------------------------------------------------------------"""
        coordinate_names = variable.get_coordinate_names()
        return [self.coords.get(coord_name) for coord_name in coordinate_names]

    def get_variable_shape(self, variable: VariableDefinition) -> Tuple[int]:
        coordinates = self.get_coordinates(variable)
        shape = tuple([coord.get_shape()[0] for coord in coordinates])
        return shape

    def extract_data(self, variable: VariableDefinition, raw_dataset: xr.Dataset) -> None:
        """-------------------------------------------------------------------
        Adds data from the xarray dataset to the given VariableDefinition. It 
        can convert units and use _FillValue to initilize variables not taken 
        from the dataset.

        Args:
            variable (VariableDefinition): The VariableDefinition to update.
            raw_dataset (xr.Dataset): The dataset to draw data from.
        -------------------------------------------------------------------"""
        # If variable is predefined, it should already have the appropriate 
        # represention in the definition; do nothing.
        if variable.is_predefined():
            dtype = variable.get_data_type()
            variable.data = np.array(variable.data, dtype=dtype)
        
        # If variable has no input, retrieve its _FillValue and shape, then 
        # initialize the data in the VariableDefinition.
        elif variable.is_derived():
            if variable.is_coordinate():
                # TODO: Warning instead of exception, skip initialization
                raise Exception("Error: coordinate variable {variable.name} must not be empty")
            shape = self.get_variable_shape(variable)
            _FillValue = variable.get_FillValue()
            dtype = variable.get_data_type()
            variable.data = np.full(shape, _FillValue, dtype=dtype)
        
        # If variable has input and is in the dataset, then convert units and 
        # add it to the VariableDefinition
        elif variable.has_input():
            input_name = variable.get_input_name()
            data = raw_dataset[input_name].values
            converted = variable.input.converter.run(data, variable.get_input_units(), variable.get_output_units())
            variable.data = converted

    def to_dict(self) -> Dict:
        """-------------------------------------------------------------------
        Returns a dictionary that can be used to instantiate an xarray dataset 
        with no data.

        Returns a dictionary like:
        ```
        {
            "coords": {"time": {"dims": ["time"], "data": [], "attrs": {"units": "seconds since 1970-01-01T00:00:00"}}},
            "attrs": {"title": "Ocean Temperature and Salinity"},
            "dims": "time",
            "data_vars": {
                "temperature": {"dims": ["time"], "data": [], "attrs": {"units": "degC"}},
                "salinity": {"dims": ["time"], "data": [], "attrs": {"units": "kg/m^3"}},
            },
        }
        ```

        Returns:
            Dict: A dictionary representing the structure of the dataset.
        -------------------------------------------------------------------"""
        dictionary = {
            "coords":       {coord_name: coord.to_dict() for coord_name, coord in self.coords.items()},
            "attrs":        {attr_name: attr.value for attr_name, attr in self.attrs.items()},
            "dims":         list(self.dims.keys()),
            "data_vars":    {var_name: var.to_dict() for var_name, var in self.vars.items()}
        }
        return dictionary

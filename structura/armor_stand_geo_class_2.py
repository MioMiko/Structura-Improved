"""generating geo.json file and texture file for each model"""

from collections import Counter,deque
import json
from typing import NewType
import numpy as np
from PIL import Image

debug = False

FilePath = NewType("FilePath",str)
Direction = NewType("Direction",str)

class default_key_dict(dict):
    def __missing__(self,key):
        return self["default"]

class Geometry:
    """
    Generate the geometry file and the texture file,
    which are the most important sections in the pack

    Attributes:
        name (str): model name
        uv_deque (deque[np.ndarray]):
            stores each used image in the deque,
            which will be poped to merge a spirite when being exported
        uv_map (dict[FilePath, int]): record the offset of each image in spirite
        uv_height (int): current spirite uv_height
        stand (dict): the entire geometry data, which will be dumped to json
        geometry (dict): a reference to self.stand['minecraft:geometry'][0]
    """

    __slots__ = ("name","stand","offsets","alpha","geometry","uv_map",
                 "material_list","uv_height","uv_deque")

    with open("lookups/block_rotation.json",encoding="utf-8") as f:
        block_rotations = json.load(f)
    with open("lookups/block_shapes.json",encoding="utf-8") as f:
        block_shapes = json.load(f)
    with open("lookups/block_uv.json",encoding="utf-8") as f:
        block_uv = json.load(f)
    with open("lookups/block_ref.json",encoding="utf-8") as f:
        block_ref = json.load(f)

    def __init__(self, name:str, alpha:float = 0.8, offsets=(0,0,0)):
        self.name = name.replace(" ","_").lower()
        self.offsets = (
            (offsets[0]+0.5) * 16,
            (offsets[1]) * 16,
            (offsets[2]-0.5) * 16
        )
        self.alpha = alpha
        self._stand_init()
        self.uv_map: dict[FilePath,int] = {}
        self.material_list = Counter()
        self.uv_height = 0
        self.uv_deque: deque[np.ndarray] = deque()

    def _stand_init(self) -> None:
        """helper function to initialize the dictionary that will be exported as the json object"""

        self.stand = {
            "format_version": "1.12.0",
            "minecraft:geometry": ({
                "description": {
                    "identifier": f"geometry.armor_stand.ghost_blocks_{self.name}",
                    "texture_width": 16,
                    "visible_bounds_offset": (0.0,1.5,0.0),
                    "visible_bounds_width" : 5120,
                    "visible_bounds_height" : 5120,
                },
                "bones": [{"name": "ghost_blocks","pivot": (-8,0,8)}]
            },)
        }
        self.geometry = self.stand['minecraft:geometry'][0]

    def export(self, zip_file) -> None:
        """
        This exporter just packs up the armorstand json files and dumps them where it should go
        As well as exports the UV file
        """

        self.geometry["description"]["texture_height"] = self.uv_height

        zip_file.writestr(
            f"models/entity/armor_stand.ghost_blocks_{self.name}.geo.json",
            json.dumps(self.stand, indent = 2 if debug else None))

        self._save_uv(f"textures/entity/ghost_blocks_{self.name}.png",
                      zip_file)

    def _save_uv(self, name, zip_file) -> None:
        """pop uv to make sprite and save it"""

        if self.uv_height == 0:
            print("No Blocks Were found")
        else:
            end = 0
            sprite = np.ones((self.uv_height,16,4),np.uint8) * 255
            while self.uv_deque:
                uv = self.uv_deque.popleft()
                start = end
                end += uv.shape[0]
                sprite[start:end, :uv.shape[1], :uv.shape[2]] = uv
            sprite[:,:,3] =  sprite[:,:,3] * self.alpha
            im = Image.fromarray(sprite)
            with zip_file.open(name, "w") as f:
                im.save(f, format="png")

    def make_layer(self, y:int) -> None:
        """
        Sets up a layer for us to refference in the animation controller later 
        Layers are moved during the poses
        """

        self.geometry["bones"].append(
            {"name": f"layer_{y}", "pivot": (-8, 0, 8), "parent": "ghost_blocks"})

    def _add_material(self, name, variant, lit, data) -> None:
        material = None
        block_ref = self.block_ref[name]
        if lit and (variant+"_lit" in block_ref) and (
                                        "material" in block_ref[variant+"_lit"]):
            material = block_ref[variant+"_lit"]["material"]
        elif (variant in block_ref) and ("material" in block_ref[variant]):
            material = block_ref[variant]["material"]
        elif  ("default" in block_ref) and ("material" in block_ref["default"]):
            material = block_ref["default"]["material"]
        else:
            material_name = name + (
                            f"_{variant}" if variant != "default" else "") + (
                            "_lit" if lit else "")
            self.material_list[material_name] += 1
            return

        if material is not None:
            for material_name, data_list in material.items():
                self.material_list[material_name] += default_key_dict(data_list)[data]

    def make_block(self , pos: tuple[int, int, int], block, make_list:bool) -> None:
        """
        Make_block handles all the block processing.
        """

        x, y, z = pos
        block_name, rot, variant, lit, data = block

        if debug:
            print(block_name,variant)

        if make_list:
            self._add_material(block_name, variant, lit, data)

        block_ref = self.block_ref[block_name]
        if len(block_ref["definition"]) == 1:
            shape = uv = rot_type = block_ref["definition"][0]
        else:
            shape, uv, rot_type = block_ref["definition"]

        if shape is None:
            return

        # hardcoded exceptions
        if uv == "glazed_terracotta":
            data = rot

        if debug and data != "0":
            print(data)

        block_uv = default_key_dict(self.block_uv[uv])[data]
        block_shapes = default_key_dict(self.block_shapes[shape])[data]

        pivot = (
            -x*16 - self.offsets[0] + 8,
            y*16 + self.offsets[1] + 8,
            z*16 + self.offsets[2] + 8
        )
        block = {
            "name": f"block_{x}_{y}_{z}",
            "cubes": [],
            "parent": f"layer_{y%12}"
        }

        if rot_type in self.block_rotations.keys():
            block["rotation"] = self.block_rotations[rot_type].get(rot,(0,0,0))
            block["pivot"] = pivot
            if debug:
                print(f"no rotation for {block_name} found")

        uv_idx = 0
        for i in range(len(block_shapes["size"])):
            cube = {}
            if len(block_uv["uv_sizes"]["up"]) > i:
                uv_idx = i
            xoff = yoff = zoff = 0
            if "offsets" in block_shapes.keys():
                xoff, yoff, zoff = block_shapes["offsets"][i]
            cube["size"] = block_shapes["size"][i]
            cube["origin"] = (
                -x*16 + xoff - self.offsets[0],
                y*16 + yoff + self.offsets[1],
                z*16 + zoff + self.offsets[2]
            )
            cube["inflate"] = -0.5
            if "rot" in block_shapes:
                cube["pivot"] = list(pivot)
                cube["rotation"] = block_shapes["rot"][i]
            if "pivot" in block_shapes:
                cube["pivot"][0] += block_shapes["pivot"][i][0]
                cube["pivot"][1] += block_shapes["pivot"][i][1]
                cube["pivot"][2] += block_shapes["pivot"][i][2]

            cube_uv = self._block_name_to_uv(block_ref,variant,lit,index=i)
            for direction, offset in block_uv["offset"].items():
                cube_uv[direction]["uv"][0] += offset[uv_idx][0]
                cube_uv[direction]["uv"][1] += offset[uv_idx][1]
            uv_size = block_uv["uv_sizes"]
            for direction in tuple(cube_uv):
                if uv_size[direction][uv_idx] is None:
                    cube_uv.pop(direction)
                    continue
                cube_uv[direction]["uv_size"] = uv_size[direction][uv_idx]

            cube["uv"] = cube_uv
            block["cubes"].append(cube)

        self.geometry["bones"].append(block)

    def _append_uv_image(self, new_image_filename: str) -> int:
        """
        Push uv to the deque

        Returns:
            int:
                The height of the uv in sprite
        """

        img = np.array(Image.open(new_image_filename))
        shape = img.shape
        if shape[1] > 16:
            img = img[:,0:16,:]
        # print(new_image_filename)
        # print(img)

        self.uv_height += shape[0]
        self.uv_deque.append(img)
        return self.uv_height - shape[0]

    def _block_name_to_uv(self, block_ref, variant="default", lit=False, index=0):
        """
        Add image to the sprite if the image never be added before
            and record its offset in the sprite in uv_map attribute
        If the image is added before return its offset directly

        Returns:
            dict[Direction, int]:
                Values: offset of the image
        """

        temp_uv: dict[Direction, int] = {}
        texture_files: dict[Direction, FilePath] = (
            self._get_block_texture_paths(block_ref,variant,lit,index))

        for key,uv in texture_files.items():
            if uv not in self.uv_map:
                self.uv_map[uv] = self._append_uv_image(f"lookups/uv/blocks/{uv}.png")
            temp_uv[key] = {"uv": [0, self.uv_map[uv]]}

        return temp_uv

    def _get_block_texture_paths(self, block_ref, variant = "",lit=False,
                                 index=0) -> dict[Direction, FilePath]:
        """
        Getting the texture file locations by given info

        Returns (dict[Direction, FilePath]):
            Textures' path for each direction
        """

        if not (lit and (texture_layout := block_ref.get(variant+"_lit"))):
            texture_layout = default_key_dict(block_ref)[variant]
        texture_layout = texture_layout["textures"]
        textures: dict[Direction, FilePath] = {}

        if isinstance(texture_layout,dict):
            if index >= (i := len(texture_layout["up"])):
                index = i - 1
            if "side" in texture_layout.keys():
                textures["east"] = texture_layout["side"][index]
                textures["west"] = texture_layout["side"][index]
                textures["north"] = texture_layout["side"][index]
                textures["south"] = texture_layout["side"][index]
            if "east" in texture_layout.keys():
                textures["east"] = texture_layout["east"][index]
            if "west" in texture_layout.keys():
                textures["west"] = texture_layout["west"][index]
            if "north" in texture_layout.keys():
                textures["north"] = texture_layout["north"][index]
            if "south" in texture_layout.keys():
                textures["south"] = texture_layout["south"][index]
            if "down" in texture_layout.keys():
                textures["down"] = texture_layout["down"][index]
            if "up" in texture_layout.keys():
                textures["up"] = texture_layout["up"][index]
        elif isinstance(texture_layout,list):
            if index >= (i := len(texture_layout)):
                index = i - 1
            textures["east"] = texture_layout[index]
            textures["west"] = texture_layout[index]
            textures["north"] = texture_layout[index]
            textures["south"] = texture_layout[index]
            textures["up"] = texture_layout[index]
            textures["down"] = texture_layout[index]

        return textures

import os, sys
from pathlib import Path
from datasets.DecaDataModule import NoWVal, NoWTest
from omegaconf import OmegaConf, DictConfig
from models.DECA import DecaModule, DECA
from train_deca_modular import locate_checkpoint
from interactive_deca_decoder import hack_paths, load_deca
import numpy as np
import torch
from skimage.io import imread, imsave
from skimage.transform import estimate_transform, warp, resize, rescale
import matplotlib.pyplot as plt
from tqdm import auto
from utils.DecaUtils import write_obj


class NowDataset(torch.utils.data.Dataset):

    def __init__(self, path, image_size, mode,
                 scale=1.6
                 # scale=1.0
                 ):
        super().__init__()
        if mode not in ['all', 'val', 'test']:
            raise ValueError(f"Invalid mode: '{mode}'. Supported modes are: 'all', 'val', 'test'")
        self.image_size = image_size
        self.scale = scale
        self.path = Path(path)
        self.subjects = sorted([p.name for p in (self.path / "iphone_pictures").glob("*") if p.is_dir()])
        # self.image_paths = sorted([p for p in (self.path / "iphone_pictures").rglob("*.(jpg|jpeg|png)") if p.is_file()])
        self.image_paths = sorted([p for p in (self.path / "iphone_pictures").rglob("*.jpg") if p.is_file()])
        self.mode = mode
        if mode != 'all':
            val_subjects = sorted([p.name for p in (self.path / "scans").glob("*") if p.is_dir()])

            if mode == 'val':
                self.subjects = val_subjects
            elif mode == 'test':
                self.subjects = sorted(list(set(self.subjects).difference(set(val_subjects))))

            subject_set = set(self.subjects)
            for i in range(len(self.image_paths)-1, 0, -1):
                subject_id = self.image_paths[i].parents[1].name
                if subject_id not in subject_set:
                    del self.image_paths[i]

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, index):
        image_path = self.image_paths[index]
        bb_path = image_path.parents[3] / "detected_face" / image_path.parents[1].name / \
                  image_path.parents[0].name / (image_path.stem + ".npy")

        bb_data = np.load(bb_path, allow_pickle=True, encoding='latin1').item()

        left = bb_data['left']
        right = bb_data['right']
        top = bb_data['top']
        bottom = bb_data['bottom']

        image = imread(image_path)[:, :, :3]
        h, w, _ = image.shape
        image = image / 255.

        old_size = (right - left + bottom - top) / 2
        center = np.array([right - (right - left) / 2.0, bottom - (bottom - top) / 2.0])  # + old_size*0.1])
        size = int(old_size * self.scale)
        src_pts = np.array(
            [[center[0] - size / 2, center[1] - size / 2], [center[0] - size / 2, center[1] + size / 2],
             [center[0] + size / 2, center[1] - size / 2]])

        # src_pts = np.array([[top, left], [top, right], [bottom, left]])
        ## src_pts = np.array([[bottom, left], [bottom, right], [top, right]])
        ## src_pts = np.array([[top, left], [bottom, right], [top, right]])

        DST_PTS = np.array([[0, 0], [0, self.image_size - 1], [self.image_size - 1, 0]])

        tform = estimate_transform('similarity', src_pts, DST_PTS)


        dst_image = warp(image, tform.inverse, output_shape=(self.image_size, self.image_size))

        # plt.figure()
        # plt.imshow(dst_image)
        # plt.show()
        # print(f"index: {index}")

        dst_image = torch.from_numpy(dst_image.astype(np.float32).transpose(2, 0, 1)[np.newaxis, ...])

        sample = {}
        sample["image"] = dst_image
        sample["imagepath"] = str(image_path)
        sample["subject"] = image_path.parents[1].name
        sample["challenge"] = image_path.parents[0].name
        return sample


def load_data(path, image_size, ):
    # now = NoWVal(
    #     path=path,
    #     ring_elements=1,
    #     crop_size=image_size)

    now = NowDataset(path, image_size, 'val')

    # N = len(now)
    # for i in range(N):
    #     sample = now[i]
    #     print(sample["imagepath"])
    return now


def load_model(path_to_models,
              run_name,
              stage,
              relative_to_path=None,
              replace_root_path=None,
              mode='best'
              ):
    run_path = Path(path_to_models) / run_name
    with open(Path(run_path) / "cfg.yaml", "r") as f:
        conf = OmegaConf.load(f)
    deca = load_deca(conf,
              stage,
              mode,
              relative_to_path,
              replace_root_path,
              )
    return deca


def get_now_point_indices(mode='handpicked', verts=None, landmark3d=None, dense_verts=None):

    if mode == 'handpicked':
        points = []
        #1
        points += [604]
        #2
        points += [24899]
        #3
        points += [33390]
        #4
        points += [37943]
        #5
        points += [29653]
        #6
        points += [6899]
        #7
        points += [1594]
        return dense_verts[np.array(points, dtype=np.int32), ...]
    elif mode == 'flame':
        landmark_51 = landmark3d[17:, :]
        landmark_7 = landmark_51[:, [19, 22, 25, 28, 16, 31, 37]]
        landmark_7 = landmark_7.cpu().numpy()
        return landmark_7
    elif mode == 'nn_flame':
        raise NotImplementedError()
    else:
        raise ValueError(f"Invalid mode '{mode}'")


def main():
    path_to_models = '/home/rdanecek/Workspace/mount/scratch/rdanecek/emoca/finetune_deca'

    dense_template_path = '/home/rdanecek/Workspace/Repos/DECA/data/texture_data_256.npy'
    dense_template = np.load(dense_template_path, allow_pickle=True, encoding='latin1').item()

    run_name = '2021_03_25_19-42-13_DECA_training'


    stage = 'detail'
    relative_to_path = '/ps/scratch/'
    replace_root_path = '/home/rdanecek/Workspace/mount/scratch/'
    deca = load_model(path_to_models, run_name, stage, relative_to_path, replace_root_path)
    deca.eval()
    deca.cuda()
    # load_data('/home/rdanecek/Workspace/mount/scratch/face2d3d', 224)
    dataset = load_data('/home/rdanecek/Workspace/Data/now/NoW_Dataset/final_release_version/',
                        deca.deca.config.image_size)

    # use_dense_topology = False
    use_dense_topology = True

    N = len(dataset)
    if use_dense_topology:
        savefolder = Path(path_to_models) / run_name / stage / "NoW_dense"
        landmark_mode = 'handpicked'
        # landmark_mode = 'nn_flame'
    else:
        savefolder = Path(path_to_models) / run_name / stage / "NoW_flame"
        landmark_mode = 'flame'
    savefolder.mkdir(exist_ok=True)

    for i in auto.tqdm(range(N)):
        sample = dataset[i]
        for key, value in sample.items():
            if isinstance(value, torch.Tensor):
                sample[key] = value.cuda()

        with torch.no_grad():
            result_dict = deca(sample)

        res_folder = savefolder / sample["subject"] / sample["challenge"]
        res_folder.mkdir(exist_ok=True, parents=True)

        vertices, faces, texture, uvcoords, uvfaces, normal_map, dense_vertices, dense_faces, dense_colors \
            = deca.deca.create_mesh(result_dict, dense_template)

        # deca.deca.save_obj(res_folder / (Path(sample["imagepath"]).stem + ".obj"),
        #                    result_dict, dense_template, mode='detail')
        out_mesh_fname = str(res_folder / (Path(sample["imagepath"]).stem + ".obj"))
        if not use_dense_topology:
            write_obj(out_mesh_fname, vertices, faces,
                            texture=texture,
                            uvcoords=uvcoords,
                            uvfaces=uvfaces,
                            normal_map=normal_map)
        else:
            write_obj(out_mesh_fname,
                            dense_vertices,
                            dense_faces,
                            colors = dense_colors,
                            inverse_face_order=True)

        landmarks = get_now_point_indices(landmark_mode, verts=vertices, dense_verts=dense_vertices,
                                          landmark3d=result_dict['landmarks3d'][0].detach().cpu())
        np.savetxt(res_folder / (Path(sample["imagepath"]).stem + ".txt"), landmarks)



if __name__ == "__main__":
    main()
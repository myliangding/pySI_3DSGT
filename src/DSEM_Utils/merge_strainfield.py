# -------------------------------------------------------------------
# Merge and store the Strain Green's Tensor (SGT) database.
# merge *_strain_field_*.bin files generated by the SPECFEM_cartesian.
#
# Author: Liang Ding
# Email: myliang.ding@mail.utoronto.ca
# -------------------------------------------------------------------


from DSEM_Utils.strainfield_reader import read_strain_bins_by_elements
import h5py
import numpy as np
import zlib
import pickle
import os.path
import sys

NAME_SGT = 'strain_field'

def DCheck_valid_step(dir_array, str_processor, step0, step1, dstep):
    '''
    * Check and count the valid step.

    :param dir_array:       The directories containing the generated strain field.
                            MUST contain the 3 directories corresponding with the three unit forces.

    :param str_processor:   The name string of the Processor, eg:'proc0000*'.
    :param step0:           The starting step, not in second.       (int), eg: 0
    :param step1:           The ending step, not in second.         (int), eg: 6000
    :param dstep:           The interval of the time step, not in second.   (int), eg: 10
    :return:
            The array of indexes indicating the valid steps.
    '''


    valid_step_array = []
    for i_step in range(int(step0), int(step1), int(dstep)):
        b_exist = True
        # check *.bin file existence.
        for file_dir in dir_array:
            file = str(file_dir) + str(str_processor) + str("_") + str(NAME_SGT) + str("_Step_") + str(i_step) + str(".bin")
            if os.path.exists(file) == False:
                b_exist = False

        if b_exist:
            valid_step_array.append(i_step)
    n_step = len(valid_step_array)
    # save valid step
    valid_step_array = np.hstack(valid_step_array)
    if n_step == 0:
        return None
    else:
        return valid_step_array


def DMerge_SGT_2_hdf5(dir_array, str_processor, NSPEC,
                      names_GLL_arr, index_GLL_arr,
                      step0, step1, dstep,
                      save_path, n_dim=3, n_paras=6):
    '''
    * Merge the strain green's tensor.
    *
    * NO COMPRESSION !!!
    *
    * Each trace has same length.
    * output format: HDF5.

    :param dir_array:       The directories containing the generated strain field.
                            MUST contain the 3 directories corresponding with the three unit forces.

    :param str_processor:   The name string of the Processor, eg:'proc0000*'
    :param NSPEC:           The number of Spectral elements in the processor. (int), eg: 2232
    :param step0:           The starting step, not in second.       (int), eg: 0
    :param step1:           The ending step, not in second.         (int), eg: 6000
    :param dstep:           The interval of the time step, not in second.   (int), eg: 10
    :param save_path:       The output path of the .HDF5 file.
    :param n_dim:           The number of Unit forces, which is restricted to 3.
    :param n_paras:         The number of the components in each SGT, which is restricted to 6.
    :return:
    '''

    if len(dir_array) != 3:
        print("The number of force component has to be 3.")
        return False

    valid_step_array = DCheck_valid_step(dir_array, str_processor, step0, step1, dstep)
    if valid_step_array is None:
        return False

    # count the total number of the Global GLL point.
    n_gll = len(names_GLL_arr)

    # count valid steps.
    n_step = len(valid_step_array)

    # allocate a buffer
    try:
        buffer = np.zeros((n_gll, n_step, n_dim, n_paras), dtype=np.float32)
    except:
        print("!!! The minimum memory requirement is {} GB.".format(n_gll * n_step * n_dim * n_paras * 4 / 1E9))
        print("!!! Unable to allocate sufficient memory!")
        exit(-2)

    # loop for all step
    for idx, i_step in enumerate(valid_step_array):
        # data container for one step
        dat_arr_onestep = np.zeros((n_gll, n_dim, n_paras))
        # loop for 3-component, unit force X/Y/Z.
        for i_dim, file_dir in enumerate(dir_array):
            file = str(file_dir) + str(str_processor) + str("_") + str(NAME_SGT) + str("_Step_") + str(i_step) + str(
                ".bin")
            # read *.bin file [SGTs (xx, yy, zz, xy, xz, yz) in element and gll points]
            # size of eps_matrix_elements = [6 * NSPEC * 125 (NGLLX*NGLLY*NGLLZ)]
            eps_matrix_elements = read_strain_bins_by_elements(file, NSPEC, bin_type=np.float32)
            # fill in the strain tensor.
            for i_para in range(n_paras):
                dat_arr_onestep[:, i_dim, i_para] = eps_matrix_elements[
                    i_para, index_GLL_arr[:, 0], index_GLL_arr[:, 1]]

        dat_arr_onestep = np.array(dat_arr_onestep, dtype=np.float32)
        # use buffer on RAM to store data temporarily.
        buffer[:, idx, :, :] = dat_arr_onestep

    # create HDF5 file and store the SGT database.
    with h5py.File(save_path) as f:
        dst = f.create_dataset("strain_fields", shape=(n_gll, n_step, n_dim, n_paras), dtype=np.float32)
        for j_gll in range(n_gll):
            dst[j_gll] = buffer[j_gll]

    print("saved at {}!".format(save_path))
    return True



def DMerge_and_Compress_SGT(dir_array, str_processor, NSPEC, names_GLL_arr, index_GLL_arr,
                            step0, step1, dstep, save_dir, n_dim=3, n_paras=6, encoding_level=8):
    '''
        * Merge the SGT in global with encoding, and compression,
        * according to the selected GLL points indicated by the 'names_GLL_arr' and 'index_GLL_arr'

        * The process to build the SGT database includes
            (1) Extract the selected GLL pints index in global from *.ibool file.
            (2) Generate the indexes array to the selected GLL points. a set of [i_sepc, i_gll].
            (3) Extract the SGT from *_strain_field.bin files export by SEM forwarding process
                according to [i_spec, i_gll] array in step (2).
            (4) Encoding the SGT in GLL point. Convert the float32 to int16.
            (5) Compress the Encoding results using Huffman coding.
            (6) Store the SGT and info to files.

    :param dir_array:       The directories containing the generated strain field.
                            MUST contain the 3 directories corresponding with the three unit forces.

    :param str_processor:   The name string of the Processor, eg:'proc0000*'
    :param NSPEC:           The number of Spectral elements in the processor. (int), eg: 2232
    :param names_GLL_arr:   The unique global index (name) of selected GLL points. [0, 1, 2, ..., etc. ]
    :param index_GLL_arr:   The indexes array that indicate where the GLL points are. [[i_spec, i_gll], ..., etc. ]
    :param step0:           The starting step, not in second.       (int), eg: 0
    :param step1:           The ending step, not in second.         (int), eg: 6000
    :param dstep:           The interval of the time step, not in second.   (int), eg: 10
    :param save_dir:        The output directory for saving the bin and info file.
    :param n_dim:           The number of Unit forces, which is restricted to 3.
    :param n_paras:         The number of the components in each SGT, which is restricted to 6.
    :param encoding_level:  The encoding level. To convert the float to INT.
    :return:    True, if successfully save the database and info file.
    '''

    if len(dir_array) != 3:
        print("Unable to Merge non-3-components SGT.")
        return False

    valid_step_array = DCheck_valid_step(dir_array, str_processor, step0, step1, dstep)
    if valid_step_array is None:
        return False

    # count the total number of the Global GLL point.
    n_gll = len(names_GLL_arr)

    # count valid steps.
    n_step = len(valid_step_array)

    # allocate a buffer
    try:
        buffer = np.zeros((n_gll, n_step, n_dim, n_paras), dtype=np.float32)
    except:
        print("!!! The minimum memory requirement is {} GB.".format(n_gll * n_step * n_dim * n_paras * 4 / 1E9))
        print("!!! Unable to allocate sufficient memory!")
        exit(-2)

    # Extract the SGT at selected GLL points from the .bin files exported by the SEM.
    # loop for all step
    for idx, i_step in enumerate(valid_step_array):
        # data container for one step
        dat_arr_onestep = np.zeros((n_gll, n_dim, n_paras))
        # loop for 3-component, unit force X/Y/Z.
        for i_dim, file_dir in enumerate(dir_array):
            file = str(file_dir) + str(str_processor) + str("_") + str(NAME_SGT) + str("_Step_") + str(i_step) + str(
                ".bin")
            # read *.bin file [SGTs (xx, yy, zz, xy, xz, yz) in element and gll points]
            # size of eps_matrix_elements = [6 * NSPEC * 125 (NGLLX*NGLLY*NGLLZ)]
            eps_matrix_elements = read_strain_bins_by_elements(file, NSPEC, bin_type=np.float32)
            # fill in the strain tensor.
            for i_para in range(n_paras):
                dat_arr_onestep[:, i_dim, i_para] = eps_matrix_elements[
                    i_para, index_GLL_arr[:, 0], index_GLL_arr[:, 1]]

        dat_arr_onestep = np.array(dat_arr_onestep, dtype=np.float32)
        # use buffer on RAM to store data temporarily.
        buffer[:, idx, :, :] = dat_arr_onestep

    # Save the data and information to files.
    sgt_data_file = str(save_dir) + str(str_processor) + str("_sgt_data.bin")
    sgt_info_file = str(save_dir) + str(str_processor) + str("_sgt_info.pkl")

    data_offset_array = []
    data_factor_array = []
    data_index_array = []

    '''Compress and write out to the bin file (data) and pickle file (information). '''
    with open(sgt_data_file, 'wb') as fw:
        for i in range(n_gll):
            data = np.empty(0)
            tmp_data = buffer[i]
            for j in range(n_dim):
                for k in range(n_paras):
                    tmp = tmp_data[:, j, k]
                    # !!! ugly !!!, will be updated later.
                    data = np.hstack([data, tmp]).astype(np.float32)

            # 1. encoding
            # make all positive. [all amplitude >=0 ]
            offset_min = np.min(data)
            data = data - offset_min
            data_offset_array.append(offset_min)

            # Amplitude normalization => [0, 1]
            normal_factor = np.max(data)
            data = data / normal_factor
            data_factor_array.append(normal_factor)

            # encoding - convert the flota32 to uint16.
            if 8 == encoding_level:
                data = np.asarray(data * (2 ** encoding_level - 1)).astype(np.uint8)
            else:
                data = np.asarray(data * (2 ** encoding_level - 1)).astype(np.uint16)

            # 2. compress
            # numpy array to bytes
            data = np.ndarray.tobytes(data)

            # compress the byte data
            data_compress = zlib.compress(data)

            # the size of compressed SGT.
            size_compress_data = sys.getsizeof(data_compress)

            # save the beginning and length of compressed data.
            # [beginning in size, length in size]
            data_index_array.append(np.array([fw.tell(), size_compress_data]))
            fw.write(data_compress)

    # Save the information for reading the SGT database later.
    data_index_array = np.asarray(data_index_array).astype(int)
    data_offset_array = np.asarray(data_offset_array).astype(np.float)
    data_factor_array = np.asarray(data_factor_array).astype(np.float)
    with open(sgt_info_file, 'wb') as fw_info:
        pickle.dump(n_gll, fw_info)
        pickle.dump(n_step, fw_info)
        pickle.dump(n_dim, fw_info)
        pickle.dump(n_paras, fw_info)
        pickle.dump(names_GLL_arr, fw_info)
        pickle.dump(data_index_array, fw_info)
        pickle.dump(data_offset_array, fw_info)
        pickle.dump(data_factor_array, fw_info)

    # print("* SGT bin file:", sgt_data_file)
    # print("* SGT info file:", sgt_info_file)
    return True


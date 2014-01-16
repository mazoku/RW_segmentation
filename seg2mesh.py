#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Segmentation data to FE mesh.
"""

import scipy.sparse as sps
import numpy as nm
from numpy.core import intc
from numpy.linalg import lapack_lite
from genfem_base import set_nodemtx, get_snodes_uedges

# compatibility
try:
    import scipy as sc
    factorial = sc.factorial

except AttributeError:
    import scipy.misc as scm

    factorial = scm.factorial

def output(msg):
    print msg

def elems_q2t(el):

    nel, nnd = el.shape
    if nnd > 4:
        q2t = nm.array([[0, 2, 3, 6],
                        [0, 3, 7, 6],
                        [0, 7, 4, 6],
                        [0, 5, 6, 4],
                        [1, 5, 6, 0],
                        [1, 6, 2, 0]])

    else:
        q2t = nm.array([[0, 1, 2],
                        [0, 2, 3]])

    ns, nn = q2t.shape
    nel *= ns

    out = nm.zeros((nel, nn), dtype=nm.int32);

    for ii in range(ns):
        idxs = nm.arange(ii, nel, ns)

        out[idxs,:] = el[:, q2t[ii,:]]

    return nm.ascontiguousarray(out)

def smooth_mesh(points, elems, etype,
                n_iter=4, lam=0.6307, mu=-0.6347,
                weights=None, bconstr=True,
                volume_corr=False):
    """
    FE mesh smoothing.

    Based on:

    [1] Steven K. Boyd, Ralph Muller, Smooth surface meshing for automated
    finite element model generation from 3D image data, Journal of
    Biomechanics, Volume 39, Issue 7, 2006, Pages 1287-1295,
    ISSN 0021-9290, 10.1016/j.jbiomech.2005.03.006.
    (http://www.sciencedirect.com/science/article/pii/S0021929005001442)

    Parameters
    ----------
    mesh : mesh
        FE mesh.
    n_iter : integer, optional
        Number of iteration steps.
    lam : float, optional
        Smoothing factor, see [1].
    mu : float, optional
        Unshrinking factor, see [1].
    weights : array, optional
        Edge weights, see [1].
    bconstr: logical, optional
        Boundary constraints, if True only surface smoothing performed.
    volume_corr: logical, optional
        Correct volume after smoothing process.

    Returns
    -------
    coors : array
        Coordinates of mesh nodes.
    """

    def laplacian(coors, weights):

        n_nod = coors.shape[0]
        displ = (weights - sps.identity(n_nod)) * coors

        return displ

    def taubin(coors0, weights, lam, mu, n_iter):

        coors = coors0.copy()

        for ii in range(n_iter):
            displ = laplacian(coors, weights)
            if nm.mod(ii, 2) == 0:
                coors += lam * displ
            else:
                coors += mu * displ

        return coors

    def dets_fast(a):
        m = a.shape[0]
        n = a.shape[1]
        lapack_routine = lapack_lite.dgetrf
        pivots = nm.zeros((m, n), intc)
        flags = nm.arange(1, n + 1).reshape(1, -1)
        for i in xrange(m):
            tmp = a[i]
            lapack_routine(n, n, tmp, n, pivots[i], 0)
        sign = 1. - 2. * (nm.add.reduce(pivots != flags, axis=1) % 2)
        idx = nm.arange(n)
        d = a[:, idx, idx]
        absd = nm.absolute(d)
        sign *= nm.multiply.reduce(d / absd, axis=1)
        nm.log(absd, absd)
        logdet = nm.add.reduce(absd, axis=-1)

        return sign * nm.exp(logdet)

    def get_volume(el, nd):

        dim = nd.shape[1]
        nnd = el.shape[1]

        etype = '%d_%d' % (dim, nnd)
        if etype == '2_4' or etype == '3_8':
            el = elems_q2t(el)

        nel = el.shape[0]

        #bc = nm.zeros((dim, ), dtype=nm.double)
        mul = 1.0 / factorial(dim)
        if dim == 3:
            mul *= -1.0

        mtx = nm.ones((nel, dim + 1, dim + 1), dtype=nm.double)
        mtx[:,:,:-1] = nd[el,:]
        vols = mul * dets_fast(mtx.copy()) # copy() ???
        vol = vols.sum()
        bc = nm.dot(vols, mtx.sum(1)[:,:-1] / nnd)

        bc /= vol

        return vol, bc


    n_nod = points.shape[0]

    if weights is None:
        # initiate all vertices as inner - hierarchy = 2
        node_group = nm.ones((n_nod,), dtype=nm.int8) * 2
        sndi, edges = get_snodes_uedges(elems, etype)
        # boundary vertices - set hierarchy = 4
        if bconstr:
            node_group[sndi] = 4

        # generate costs matrix
        end1 = edges[:,0]
        end2 = edges[:,1]
        idxs = nm.where(node_group[end2] >= node_group[end1])
        rows1 = end1[idxs]
        cols1 = end2[idxs]
        idxs = nm.where(node_group[end1] >= node_group[end2])
        rows2 = end2[idxs]
        cols2 = end1[idxs]
        crows = nm.concatenate((rows1, rows2))
        ccols = nm.concatenate((cols1, cols2))
        costs = sps.coo_matrix((nm.ones_like(crows), (crows, ccols)),
                               shape=(n_nod, n_nod),
                               dtype=nm.double)

        # generate weights matrix
        idxs = range(n_nod)
        aux = sps.coo_matrix((1.0 / nm.asarray(costs.sum(1)).squeeze(),
                              (idxs, idxs)),
                             shape=(n_nod, n_nod),
                             dtype=nm.double)

        #aux.setdiag(1.0 / costs.sum(1))
        weights = (aux.tocsc() * costs.tocsc()).tocsr()

    coors = taubin(points, weights, lam, mu, n_iter)

    if volume_corr:
        volume0, bc = get_volume(elems, points)
        volume, _ = get_volume(elems, points)

        scale = volume0 / volume
        coors = (coors - bc) * scale + bc

    return coors

def gen_mesh_from_voxels(voxels, dims, etype='q', mtype='v'):
    """
    Generate FE mesh from voxels (volumetric data).

    Parameters
    ----------
    voxels : array
        Voxel matrix, 1=material.
    dims : array
        Size of one voxel.
    etype : integer, optional
        'q' - quadrilateral or hexahedral elements
        't' - triangular or tetrahedral elements
    mtype : integer, optional
        'v' - volumetric mesh
        's' - surface mesh

    Returns
    -------
    mesh : Mesh instance
        Finite element mesh.
    """

    dims = dims.squeeze()
    dim = len(dims)
    nddims = nm.array(voxels.shape) + 2

    nodemtx = nm.zeros(nddims, dtype=nm.int8)
    vxidxs = nm.where(voxels)
    set_nodemtx(nodemtx, vxidxs, etype)

    ndidx = nm.where(nodemtx)
    del(nodemtx)

    coors = nm.array(ndidx).transpose() * dims
    nnod = coors.shape[0]

    nodeid = -nm.ones(nddims, dtype=nm.int32)
    nodeid[ndidx] = nm.arange(nnod)

    if mtype == 's':
        felems = []
        nn = nm.zeros(nddims, dtype=nm.int8)

    # generate elements
    if dim == 2:
        ix, iy = vxidxs

        if mtype == 'v':
            elems = nm.array([nodeid[ix,iy],
                              nodeid[ix + 1,iy],
                              nodeid[ix + 1,iy + 1],
                              nodeid[ix,iy + 1]]).transpose()
            edim = 2

        else:
            fc = nm.zeros(nddims + (2,), dtype=nm.int32)

            # x
            fc[ix,iy,:] = nm.array([nodeid[ix,iy + 1],
                                    nodeid[ix,iy]]).transpose()
            fc[ix + 1,iy,:] = nm.array([nodeid[ix + 1,iy],
                                        nodeid[ix + 1,iy + 1]]).transpose()
            nn[ix,iy] = 1
            nn[ix + 1,iy] += 1

            idx = nm.where(nn == 1)
            felems.append(fc[idx])

            # y
            fc.fill(0)
            nn.fill(0)
            fc[ix,iy,:] = nm.array([nodeid[ix,iy],
                                    nodeid[ix + 1,iy]]).transpose()
            fc[ix,iy + 1,:] = nm.array([nodeid[ix + 1,iy + 1],
                                        nodeid[ix,iy + 1]]).transpose()
            nn[ix,iy] = 1
            nn[ix,iy + 1] += 1

            idx = nm.where(nn == 1)
            felems.append(fc[idx])

            elems = nm.concatenate(felems)

            edim = 1

    elif dim == 3:
        ix, iy, iz = vxidxs

        if mtype == 'v':
            elems = nm.array([nodeid[ix,iy,iz],
                              nodeid[ix + 1,iy,iz],
                              nodeid[ix + 1,iy + 1,iz],
                              nodeid[ix,iy + 1,iz],
                              nodeid[ix,iy,iz + 1],
                              nodeid[ix + 1,iy,iz + 1],
                              nodeid[ix + 1,iy + 1,iz + 1],
                              nodeid[ix,iy + 1,iz + 1]]).transpose()
            edim = 3

        else:
            fc = nm.zeros(tuple(nddims) + (4,), dtype=nm.int32)

            # x
            fc[ix,iy,iz,:] = nm.array([nodeid[ix,iy,iz],
                                       nodeid[ix,iy,iz + 1],
                                       nodeid[ix,iy + 1,iz + 1],
                                       nodeid[ix,iy + 1,iz]]).transpose()
            fc[ix + 1,iy,iz,:] = nm.array([nodeid[ix + 1,iy,iz],
                                           nodeid[ix + 1,iy + 1,iz],
                                           nodeid[ix + 1,iy + 1,iz + 1],
                                           nodeid[ix + 1,iy,iz + 1]]).transpose()
            nn[ix,iy,iz] = 1
            nn[ix + 1,iy,iz] += 1

            idx = nm.where(nn == 1)
            felems.append(fc[idx])

            # y
            fc.fill(0)
            nn.fill(0)
            fc[ix,iy,iz,:] = nm.array([nodeid[ix,iy,iz],
                                       nodeid[ix + 1,iy,iz],
                                       nodeid[ix + 1,iy,iz + 1],
                                       nodeid[ix,iy,iz + 1]]).transpose()
            fc[ix,iy + 1,iz,:] = nm.array([nodeid[ix,iy + 1,iz],
                                           nodeid[ix,iy + 1,iz + 1],
                                           nodeid[ix + 1,iy + 1,iz + 1],
                                           nodeid[ix + 1,iy + 1,iz]]).transpose()
            nn[ix,iy,iz] = 1
            nn[ix,iy + 1,iz] += 1

            idx = nm.where(nn == 1)
            felems.append(fc[idx])

            # z
            fc.fill(0)
            nn.fill(0)
            fc[ix,iy,iz,:] = nm.array([nodeid[ix,iy,iz],
                                       nodeid[ix,iy + 1,iz],
                                       nodeid[ix + 1,iy + 1,iz],
                                       nodeid[ix + 1,iy,iz]]).transpose()
            fc[ix,iy,iz + 1,:] = nm.array([nodeid[ix,iy,iz + 1],
                                           nodeid[ix + 1,iy,iz + 1],\
                                           nodeid[ix + 1,iy + 1,iz + 1],
                                           nodeid[ix,iy + 1,iz + 1]]).transpose()
            nn[ix,iy,iz] = 1
            nn[ix,iy,iz + 1] += 1

            idx = nm.where(nn == 1)
            felems.append(fc[idx])

            elems = nm.concatenate(felems)

            edim = 2

    # reduce inner nodes
    if mtype == 's':
        aux = nm.zeros((nnod,), dtype=nm.int32)

        for ii in elems.T:
            aux[ii] = 1

        idx = nm.where(aux)

        aux.fill(0)
        nnod = idx[0].shape[0]

        aux[idx] = range(nnod)
        coors = coors[idx]

        for ii in range(elems.shape[1]):
            elems[:,ii] = aux[elems[:,ii]]

    if etype == 't':
        elems = elems_q2t(elems)

    nel = elems.shape[0]
    nelnd = elems.shape[1]

    etype = '%d_%d' % (edim, nelnd)
    return coors, nm.ascontiguousarray(elems), etype

def mesh2vtk(points, elements, etype):
    import vtk

    elems_t = {
        '2_3': vtk.VTK_TRIANGLE,
        '2_4': vtk.VTK_QUAD,
        '3_4': vtk.VTK_TETRA,
        '3_8': vtk.VTK_HEXAHEDRON,
        }

    vtkpoints = vtk.vtkPoints()
    for ii in points:
        vtkpoints.InsertNextPoint(ii)

    grid = vtk.vtkUnstructuredGrid()
    grid.SetPoints(vtkpoints)

    for ii in elements:
        ptids = vtk.vtkIdList()
        for jj in range(len(ii)):
            ptids.InsertId(jj, int(ii[jj]))
            grid.InsertNextCell(elems_t[etype], ptids)

    return grid
